"""Answer generation for one CSV row. Every row is independent; no state of a dialogue is shared."""
from dataclasses import asdict
import json
import re
import threading
import time

from dialogue import parse_question, retrieval_query
from dialogue_n1 import parse_dialogue
from llm_client import ModelError
from prompts import DOCUMENTS_HEADER, HIGHLIGHT_HEADER, REFERENCE_HEADER, system_prompt, user_prompt
from prompts_a2 import ANSWER_PROMPT as A2_PROMPT
from retrieval import WideRetriever
from retrieval_a2 import LexicalRetriever, load_fragments

# Used only by the A2 control mode, byte-for-byte the A2 text.
TECHNICAL_ANSWER = ("Сейчас не удалось получить ответ модели из-за технического сбоя. "
                    "Это не означает, что информации нет в базе знаний. "
                    "Попробуйте повторить вопрос позже; заявку пока не отправляли.")
LAST_RESORT = ("Чтобы ответить точно, нам нужно немного больше сведений о вашей задаче и объекте: тип организации, "
               "присоединённая мощность и то, что уже установлено из приборов учёта. Расскажите, пожалуйста, подробнее — "
               "или оставьте телефон, и вопрос разберёт специалист МТС EnergyTool.")
META_HEADINGS = ("Чего утверждать нельзя", "Факты, которые можно утверждать", "Что мы не делаем", "Следующий шаг")


def sanitize_delivery_a2(answer):
    """A2 behaviour, kept only for the control mode."""
    sent_claim = re.search(r"(?:заявк\w*\s+(?:успешно\s+)?(?:отправлен|передан)|"
                           r"(?:отправил|передал)\w*\s+(?:ваш\w*\s+)?заявк)", answer, re.I)
    if sent_claim:
        answer = re.sub(r"[^.!?\n]*" + re.escape(sent_claim.group(0)) + r"[^.!?\n]*[.!?]?",
                        "Заявку можно подготовить; отправки менеджеру пока нет.", answer, flags=re.I)
    return answer.strip()


def unwrap(answer):
    """Tolerate an answer wrapped in a code fence or a {"answer": ...} object."""
    candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer.strip(), flags=re.I).strip()
    if candidate.startswith("{"):
        try:
            wrapper = json.loads(candidate)
            if isinstance(wrapper, dict) and isinstance(wrapper.get("answer"), str):
                return wrapper["answer"].strip()
        except (ValueError, TypeError):
            pass
    return candidate if candidate else answer.strip()


def polish(answer):
    """Plain single-paragraph text, without role labels or markup; no claim that a lead was sent."""
    text = unwrap(answer)
    text = re.sub(r"^\s*(?:\*\*)?(?:Консультант|Ассистент|Ответ|Assistant)(?:\*\*)?\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"(?m)^\s*(?:[-•*]|\d+[.)])\s+", "", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = " ".join(text.split())
    if len(text) > 1 and text[0] in "«\"“" and text[-1] in "»\"”" and text.count(text[0]) == 1:
        text = text[1:-1].strip()
    text = re.sub(r"\b([Зз]аявка)\s+(?:уже\s+|успешно\s+)*(?:отправлена|передана)\b", r"\1 сформирована", text)
    text = re.sub(r"\b(отправил|передал)(а?)\s+((?:ваш\w*\s+)?заявк\w+)", r"сформировал\2 \3", text)
    if len(text) > 9900:
        cut = max(text.rfind(". ", 0, 9900), text.rfind("? ", 0, 9900), text.rfind("! ", 0, 9900))
        text = text[:cut + 1] if cut > 0 else text[:9900]
    return text.strip()


LADDER = ("full", "docs", "wide")


class RunState:
    """Shared, thread-safe switches learned during one run."""
    def __init__(self, start):
        self._lock = threading.Lock()
        self.level = LADDER.index(start) if start in LADDER else len(LADDER) - 1
        self.start_level = self.level
        self.fast = False
        self.soft_failures = 0
        self.allowed = None   # largest prompt, in characters, believed to fit the context window of the service

    def mode(self):
        with self._lock:
            return LADDER[self.level]

    def step_down(self, from_mode, hard=False, weight=1):
        """A large context keeps failing in transport: use the next smaller one for the following rows.

        Timeouts and service errors step down only when they come in a row (two timeouts or four
        errors without a usable answer in between). A token-limited answer never changes the context:
        its cause is the length of reasoning, not of the prompt. A prompt that does not fit the
        context window is handled separately, by sizing the context (note_refusal).
        """
        with self._lock:
            if from_mode not in LADDER or LADDER.index(from_mode) != self.level or self.level >= len(LADDER) - 1:
                return
            self.soft_failures += weight
            if hard or self.soft_failures >= 4:
                self.level += 1
                self.soft_failures = 0

    def ok(self, mode):
        """A usable answer in the current context: earlier transport failures were not systematic."""
        with self._lock:
            if mode in LADDER and LADDER.index(mode) == self.level:
                self.soft_failures = 0

    def hurry(self):
        with self._lock:
            self.fast = True
            self.level = len(LADDER) - 1

    def allowed_chars(self):
        with self._lock:
            return self.allowed

    def note_refusal(self, prompt_chars, completion=0, window=None):
        """The service refused a prompt of this size: remember how much fits.

        Exact when the refusal states the window and the prompt in tokens; otherwise the size is
        reduced by a fifth per refusal. Small prompts are not refused for their size, so they teach nothing.
        """
        if prompt_chars < 20000:
            return
        estimate = prompt_chars * 0.8
        if window:
            tokens, prompt_tokens = window
            room = tokens - completion - 256
            if room > 1000 and prompt_tokens > 0:
                estimate = min(prompt_chars * 0.97, room * prompt_chars / prompt_tokens * 0.97)
        estimate = max(int(estimate), 16000)
        with self._lock:
            if self.allowed is None or estimate < self.allowed:
                self.allowed = estimate


class Consultant:
    def __init__(self, client, knowledge_path, settings):
        self.client, self.settings = client, settings
        self.fragments = tuple(load_fragments(knowledge_path))
        self.a2 = LexicalRetriever(self.fragments)
        self.wide = WideRetriever(self.fragments)
        self.state = RunState(settings.context)
        if settings.quick:
            self.state.hurry()
        self.reference = self.wide.reference()
        style = settings.style
        self.system_compact = system_prompt(fewshot=settings.fewshot, style=style)
        self.system_full = self.system_docs = None
        if settings.prompt == "n1" and settings.context == "full":
            self.system_full = system_prompt(fewshot=settings.fewshot, knowledge=self.fragments, style=style)
        if settings.prompt == "n1" and settings.context in ("full", "docs"):
            self.system_docs = system_prompt(fewshot=settings.fewshot, knowledge=self.reference, header=REFERENCE_HEADER,
                                             style=style)

    # ---- context ---------------------------------------------------------------
    def _a2_sources(self, query):
        chosen, used, seen = [], 0, set()
        for fragment in self.a2.search(query, self.settings.top_k):
            if fragment.source_id in seen or not fragment.text.strip():
                continue
            if used + len(fragment.text) > self.settings.context_chars:
                continue
            chosen.append(fragment)
            seen.add(fragment.source_id)
            used += len(fragment.text)
        return chosen

    def _wide_sources(self, query, compact=False, budget=None):
        if compact:
            return self.wide.search(query, max(4, self.settings.wide_k - 3),
                                    min(self.settings.wide_chars, 9000) if budget is None else budget)
        return self.wide.search(query, self.settings.wide_k, self.settings.wide_chars if budget is None else budget)

    def _build(self, messages, query, mode, *, fast=False, compact=False):
        """Return (chat messages, context characters) for a context mode.

        When the run has learned the context window of the service, the documents and fragments are
        sized to fit it; None means that this mode cannot fit and the caller takes the next smaller one.
        """
        cfg = self.settings
        if cfg.prompt == "a2":
            sources = (self._a2_sources(query) if mode == "a2" else
                       list(self.fragments) if mode == "full" else
                       self.reference + self.wide.search_documents(query, cfg.doc_count, cfg.doc_k, cfg.doc_chars)
                       if mode == "docs" else self._wide_sources(query, compact))
            context = {"messages": [{"index": i, **asdict(m)} for i, m in enumerate(messages)],
                       "sources": [{"source_id": f.source_id, "text": f.text} for f in sources]}
            return ([{"role": "system", "content": A2_PROMPT},
                     {"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
                    sum(len(f.text) for f in sources))
        allowed = self.state.allowed_chars()

        def excess(chat):
            return sum(len(m["content"]) for m in chat) - allowed if allowed else 0

        if mode == "full":
            highlight = self.wide.ordered(self.wide.search(query, 8, 9000))
            chat = [{"role": "system", "content": self.system_full},
                    {"role": "user", "content": user_prompt(messages, highlight, header=HIGHLIGHT_HEADER, fast=fast)}]
            return None if excess(chat) > 0 else (chat, sum(len(f.text) for f in self.fragments))
        if mode == "docs":
            budget = cfg.doc_chars
            for _ in range(4):
                sources = self.wide.search_documents(query, cfg.doc_count, cfg.doc_k, budget)
                chat = [{"role": "system", "content": self.system_docs},
                        {"role": "user", "content": user_prompt(messages, sources, header=DOCUMENTS_HEADER, fast=fast)}]
                used = sum(len(f.text) for f in sources)
                over = excess(chat)
                if over <= 0:
                    return chat, used + sum(len(f.text) for f in self.reference)
                budget = used - over - 400
                if budget < 8000:
                    break
            return None
        if mode == "a2":
            sources = self._a2_sources(query)
            return ([{"role": "system", "content": self.system_compact},
                     {"role": "user", "content": user_prompt(messages, sources, fast=fast)}],
                    sum(len(f.text) for f in sources))
        budget = min(cfg.wide_chars, 9000) if compact else cfg.wide_chars
        while True:
            sources = self.wide.ordered(self._wide_sources(query, compact, budget))
            chat = [{"role": "system", "content": self.system_compact},
                    {"role": "user", "content": user_prompt(messages, sources, fast=fast)}]
            over = excess(chat)
            if over <= 0 or budget <= 3000:
                return chat, sum(len(f.text) for f in sources)   # the smallest context is always tried
            budget = max(3000, budget - over - 300)

    # ---- generation --------------------------------------------------------------
    def answer(self, question, *, deadline=None):
        """Return (answer, info). `info` holds only safe metadata for diagnostics."""
        cfg = self.settings
        info = {"status": "ok", "mode": cfg.context, "calls": 0, "finish": "", "reasoning_chars": 0,
                "completion_tokens": 0, "context_chars": 0, "error": None}
        try:
            # The control mode keeps the A2 parser; the N1 modes also read other speaker labels.
            messages = parse_question(question) if cfg.control else parse_dialogue(question)
            query = retrieval_query(messages)
        except Exception:
            info.update(status="input_error", error="parse")
            return (TECHNICAL_ANSWER if not cfg.rescue else LAST_RESORT), info

        def call(mode, *, fast=False, compact=False, reasoning=None, max_tokens=None, retry=False, built=None):
            chat, chars = built or self._build(messages, query, mode, fast=fast, compact=compact)
            info["calls"] += 1
            info["mode"], info["context_chars"] = mode, chars
            info["prompt_chars"] = sum(len(m["content"]) for m in chat)
            big = mode in ("full", "docs")
            done = self.client.chat(chat, deadline=deadline,
                                    max_tokens=cfg.main_max_tokens if max_tokens is None else max_tokens,
                                    reasoning=cfg.reasoning if reasoning is None else reasoning,
                                    # The second try may generate twice as much: one attempt, the general time limit.
                                    attempts=1 if retry else 2 if big else None,
                                    timeout=cfg.big_timeout if big and not retry else None)
            info.update(finish=done.finish_reason, reasoning_chars=done.reasoning_chars,
                        completion_tokens=done.completion_tokens)
            return done

        if not cfg.rescue:
            return self._control(call, info)

        fast = self.state.fast
        mode = self.state.mode() if cfg.context in LADDER else cfg.context

        def plan(mode):
            """Steps for one row: the main request; a second try in the SAME context with a larger
            budget and briefer reasoning; a compact request without reasoning as the last model call."""
            steps = [dict(mode=mode, fast=fast, reasoning="off" if fast else None)]
            if cfg.retry_tokens:
                steps.append(dict(mode=mode, fast=True, reasoning="off" if fast else cfg.retry_reasoning, retry=True,
                                  max_tokens=max(cfg.retry_tokens, cfg.main_max_tokens)))
            steps.append(dict(mode="wide", fast=True, compact=True, reasoning="off"))
            return steps

        queue = plan(mode)
        partial, steps, replans, first = "", 0, 0, True
        while queue and steps < 7:
            options = queue.pop(0)
            if deadline is not None and time.monotonic() >= deadline:
                info.update(status="deadline", error="deadline_exceeded")
                break
            large = options["mode"] in LADDER[:-1] and "compact" not in options
            built = self._build(messages, query, options["mode"], fast=options.get("fast", False),
                                compact=options.get("compact", False))
            if built is None:
                # Larger than the window learned in this run: the same plan in the next smaller context.
                if not options.get("retry"):
                    queue = plan(LADDER[LADDER.index(options["mode"]) + 1])
                continue
            steps += 1
            try:
                done = call(**options, built=built)
            except ModelError as exc:
                info["error"] = exc.code
                if exc.code == "deadline_exceeded":
                    info["status"] = "deadline"
                    break
                if exc.status in (401, 403):
                    break  # an access error will not heal within this row
                refused = exc.context_overflow or exc.code == "bad_request"
                if refused and options["mode"] in LADDER and "compact" not in options \
                        and not options.get("retry") and replans < 5:
                    # The prompt did not fit: learn the window and build the same step again, sized to it.
                    replans += 1
                    before = self.state.allowed_chars()
                    self.state.note_refusal(info.get("prompt_chars", 0), exc.limit, exc.window)
                    resized = cfg.prompt == "n1" and self.state.allowed_chars() != before
                    if resized or large:
                        queue = plan(options["mode"] if resized else LADDER[LADDER.index(options["mode"]) + 1])
                elif large and not options.get("retry") and not refused:
                    self.state.step_down(options["mode"], weight=2 if exc.code in ("transport_error", "timeout") else 1)
                continue
            if done.usable:
                text = polish(done.content)
                if text:
                    info["status"] = ("retried" if options.get("retry") else
                                      "recovered" if "compact" in options or not first else "ok")
                    info["error"] = None
                    self.state.ok(options["mode"])
                    return text, info
            first = False
            info["error"] = "truncated" if done.truncated else "empty"
            if done.truncated and len(done.content.split()) >= 12:
                partial = done.content
        if partial:
            # A token-limited answer cut at its last complete sentence is still the model's own grounded text.
            text = polish(partial)
            cut = max(text.rfind(". "), text.rfind("? "), text.rfind("! "))
            if cut > 40:
                info["status"] = "partial"
                return text[:cut + 1], info
        info["status"] = "fallback" if info["status"] != "deadline" else "deadline_fallback"
        return self.extract(query), info

    def _control(self, call, info):
        """A2 policy: the same request is repeated only for empty content; no recovery."""
        cfg = self.settings
        mode = cfg.context
        for _ in range(cfg.attempts):
            try:
                done = call(mode)
            except ModelError as exc:
                info.update(status="technical_error", error=exc.code)
                return TECHNICAL_ANSWER, info
            if done.truncated:
                info.update(status="technical_error", error="truncated_response")
                return TECHNICAL_ANSWER, info
            if done.content:
                if cfg.prompt == "a2":
                    # Exactly the A2 post-processing: only a parsed JSON wrapper replaces the text.
                    answer = done.content.strip()
                    candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer, flags=re.I).strip()
                    if candidate.startswith("{"):
                        try:
                            wrapper = json.loads(candidate)
                            if isinstance(wrapper, dict) and isinstance(wrapper.get("answer"), str):
                                answer = wrapper["answer"].strip()
                        except (ValueError, TypeError):
                            pass
                    answer = sanitize_delivery_a2(answer)
                else:
                    answer = polish(done.content)
                if answer and len(answer) <= 10000:
                    return answer, info
                info.update(status="technical_error", error="invalid_answer_length")
                return TECHNICAL_ANSWER, info
        info.update(status="technical_error", error="empty_response")
        return TECHNICAL_ANSWER, info

    # ---- last resort without the model -----------------------------------------------
    def extract(self, query):
        """A grounded excerpt of the closest FAQ-style section; never a technical placeholder."""
        try:
            for index in self.wide.rank(query)[:12]:
                fragment = self.wide.fragments[index]
                heading, _, body = fragment.text.partition("\n")
                if any(h in heading for h in META_HEADINGS) or "-----" in body or "|" in body:
                    continue
                if not fragment.document_id.startswith(("20-products/", "10-energy/")):
                    continue
                text = " ".join(re.sub(r"\*\*|`|\[|\]\([^)]*\)", "", body).split())
                sentences = re.findall(r"[^.!?]+[.!?]", text)
                excerpt = ""
                for sentence in sentences:
                    if len((excerpt + sentence).split()) > 55:
                        break
                    excerpt += sentence
                if len(excerpt.split()) >= 8:
                    return (excerpt.strip() + " Чтобы ответить точнее по вашей ситуации, расскажите, пожалуйста, "
                            "подробнее об объекте и задаче.")
        except Exception:
            pass
        return LAST_RESORT

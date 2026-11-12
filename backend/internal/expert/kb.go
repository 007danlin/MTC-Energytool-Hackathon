package expert

import (
	"fmt"
	"sort"
	"strings"
	"time"
)

// KBDocument is one approved revision rendered for the web search loader.
// It carries no author, reviewer, request, session or contact data.
type KBDocument struct {
	EntryID  string `json:"entry_id"`
	Revision int    `json:"revision"`
	Path     string `json:"path"`      // 90-expert/<entry_id>-r<revision>.md
	SourceID string `json:"source_id"` // path#s001 as produced by the Markdown section loader
	Markdown string `json:"markdown"`
	Test     bool   `json:"test"`
}

// RenderForKB renders a revision as one Markdown document with a single section.
func RenderForKB(e KnowledgeEntry, rev Revision) KBDocument {
	path := fmt.Sprintf("90-expert/%s-r%d.md", e.ID, rev.Revision)
	var b strings.Builder
	fmt.Fprintf(&b, "# Ответ специалиста: %s\n\n", rev.Title)
	fmt.Fprintf(&b, "Вопрос: %s\n\n", rev.GeneralizedQuestion)
	fmt.Fprintf(&b, "Ответ: %s\n\n", rev.Answer)
	fmt.Fprintf(&b, "Применимо: %s\n\n", rev.Applicability)
	fmt.Fprintf(&b, "Основание: %s\n", rev.Basis)
	if rev.ReviewedAt != nil {
		fmt.Fprintf(&b, "\nПроверено специалистом Energytool: %s\n", rev.ReviewedAt.In(time.FixedZone("MSK", 3*3600)).Format("02.01.2006"))
	}
	return KBDocument{EntryID: e.ID, Revision: rev.Revision, Path: path, SourceID: path + "#s001",
		Markdown: b.String(), Test: e.Test}
}

// ActiveSet lists the documents the next knowledge-base version must contain:
// exactly one revision per entry (the one in force), drafts and revoked entries excluded.
// test selects the separate demo base (true) or the real base (false).
func ActiveSet(entries []KnowledgeEntry, test bool) []KBDocument {
	out := []KBDocument{}
	for _, e := range entries {
		if e.Test != test {
			continue
		}
		if rev := e.InForce(); rev != nil {
			out = append(out, RenderForKB(e, *rev))
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Path < out[j].Path })
	return out
}

// ActivationResult is reported by the core API after it rebuilt (or failed to rebuild) the search.
type ActivationResult struct {
	KBVersion string         `json:"kb_version"`
	OK        bool           `json:"ok"`
	ErrorCode string         `json:"error_code,omitempty"`
	Included  map[string]int `json:"included"` // entry id -> revision actually in kb_version
}

// ApplyActivation records the real search state for one entry (system actor). On success the
// included revision becomes active and every other one inactive; on failure pending revisions
// become failed while a previously active revision stays active (the old base still serves).
// Re-applying the same kb_version is a no-op.
func ApplyActivation(e KnowledgeEntry, actor Actor, cmd Command, result ActivationResult, now time.Time) (KnowledgeEntry, error) {
	if result.OK && result.KBVersion != "" {
		applied := true
		included := result.Included[e.ID]
		for _, r := range e.Revisions {
			want := RuntimeInactive
			if r.Revision == included {
				want = RuntimeActive
			}
			if r.Publication == PubDraft {
				continue
			}
			if r.Runtime != want || (want == RuntimeActive && r.KBVersion != result.KBVersion) {
				applied = false
			}
		}
		if applied {
			return e, nil
		}
	}
	return applyKnowledge(e, actor, cmd, fingerprint("activation", cmd.ExpectedVersion, actor, result), now,
		func(n *KnowledgeEntry) (string, int, error) {
			if actor.Role != RoleSystem {
				return "", 0, ErrForbidden
			}
			if result.KBVersion == "" && result.OK {
				return "", 0, fmt.Errorf("%w: kb_version is required", ErrInvalidInput)
			}
			included := result.Included[n.ID]
			if result.OK && included != 0 {
				found := false
				for _, r := range n.Revisions {
					found = found || (r.Revision == included && r.Publication == PubApproved)
				}
				if !found {
					return "", 0, fmt.Errorf("%w: activated revision is not approved", ErrInvalidTransition)
				}
			}
			for i := range n.Revisions {
				r := &n.Revisions[i]
				if r.Publication == PubDraft {
					continue
				}
				switch {
				case result.OK && r.Revision == included:
					r.Runtime, r.KBVersion, r.RuntimeError = RuntimeActive, result.KBVersion, ""
				case result.OK:
					if r.Runtime != RuntimeNone {
						r.Runtime, r.RuntimeError = RuntimeInactive, ""
					}
				case r.Runtime == RuntimePending:
					r.Runtime, r.RuntimeError = RuntimeFailed, truncate(result.ErrorCode, 100)
				}
			}
			action := "activation_failed"
			if result.OK {
				action = "activated"
			}
			return action, included, nil
		})
}

// AvailableToBot is true only for a revision active in a confirmed kb_version.
func AvailableToBot(e KnowledgeEntry) (Revision, bool) {
	for _, r := range e.Revisions {
		if r.Runtime == RuntimeActive && r.Publication == PubApproved && r.KBVersion != "" {
			return r, true
		}
	}
	return Revision{}, false
}

// PublicEntry hides command bookkeeping; the internal source request id stays for staff views only.
func PublicEntry(e KnowledgeEntry) KnowledgeEntry {
	out := cloneEntry(e)
	out.Commands = replayLog{}
	return out
}

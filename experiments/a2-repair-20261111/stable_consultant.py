"""A2 answer path with a narrow deterministic contact draft.

Product answers retain A2's generation and source packing. There is no catalog
planner or automatic rewriting by a second model. Format validation is not a
claim of factual verification.
"""
import time
from consultant import Consultant, seed_lead, make_summary
from contracts import ConsultationResult
from contact_flow import contact_reply


class StableConsultant(Consultant):
    def respond(self, request, *, deadline=None, answer_only=False):
        if answer_only:
            started = time.monotonic()
            request.__post_init__()
            reply = contact_reply(request.messages)
            if reply is not None:
                lead = seed_lead(request)
                return ConsultationResult(
                    reply, 'answered', [], round((time.monotonic()-started)*1000),
                    lead, False, make_summary({}, request, lead, []),
                    {'mode': 'deterministic_contact', 'error_code': None,
                     'evidence_validation': 'user_contact_only',
                     'external_delivery': False})
        result = super().respond(request, deadline=deadline, answer_only=answer_only)
        if answer_only:
            result.debug['mode'] = 'a2_repaired'
            result.debug['evidence_validation'] = 'format_only_unverified_generation'
        return result

package business

import (
	"errors"
	"fmt"
	"strings"
	"time"
	"unicode/utf8"

	"energytool/backend/internal/domain"
)

// ReviewStatus is the manager's handling state of an application.
// accepted = taken into work by a manager; it is not a contract or revenue.
type ReviewStatus string

const (
	StatusNew       ReviewStatus = "new"
	StatusInReview  ReviewStatus = "in_review"
	StatusAccepted  ReviewStatus = "accepted"
	StatusNeedsInfo ReviewStatus = "needs_info"
	StatusRejected  ReviewStatus = "rejected"
)

// ReasonCode classifies returns and rejections for metrics. Free text goes to Comment,
// which stays in the record and never enters events.
type ReasonCode string

var reasonCodes = map[ReasonCode]string{
	"missing_data":  "не хватает данных об объекте/задаче",
	"unreachable":   "не удалось связаться",
	"not_target":    "не целевой сегмент или задача вне продуктов",
	"duplicate":     "дубль обращения",
	"no_consent":    "клиент отказался продолжать",
	"manager_error": "ошибка обработки (повторное открытие)",
	"other":         "другое",
}

// ReasonCatalog returns the allowed reason codes with their Russian labels (for UI).
func ReasonCatalog() map[ReasonCode]string {
	out := make(map[ReasonCode]string, len(reasonCodes))
	for k, v := range reasonCodes {
		out[k] = v
	}
	return out
}

type Action string

const (
	ActionStartReview Action = "start_review" // new|needs_info -> in_review
	ActionAccept      Action = "accept"       // in_review -> accepted
	ActionNeedsInfo   Action = "needs_info"   // in_review -> needs_info (reason)
	ActionReject      Action = "reject"       // in_review -> rejected (reason)
	ActionReopen      Action = "reopen"       // accepted|rejected -> in_review (reason)
)

var transitions = map[Action]struct {
	from        []ReviewStatus
	to          ReviewStatus
	needsReason bool
}{
	ActionStartReview: {[]ReviewStatus{StatusNew, StatusNeedsInfo}, StatusInReview, false},
	ActionAccept:      {[]ReviewStatus{StatusInReview}, StatusAccepted, false},
	ActionNeedsInfo:   {[]ReviewStatus{StatusInReview}, StatusNeedsInfo, true},
	ActionReject:      {[]ReviewStatus{StatusInReview}, StatusRejected, true},
	ActionReopen:      {[]ReviewStatus{StatusAccepted, StatusRejected}, StatusInReview, true},
}

var (
	ErrInvalidTransition = errors.New("transition is not allowed from the current status")
	ErrReasonRequired    = errors.New("reason code is required for this action")
	ErrApplicationClosed = errors.New("application is not editable in this status")
)

type TransitionEntry struct {
	Version   int          `json:"version"`
	Action    Action       `json:"action"`
	From      ReviewStatus `json:"from"`
	To        ReviewStatus `json:"to"`
	Reason    ReasonCode   `json:"reason,omitempty"`
	Comment   string       `json:"comment,omitempty"`
	At        time.Time    `json:"at"`
	RequestID string       `json:"request_id,omitempty"`
}

// ApplicationRecord is the stored business object: one per session.
// Version grows on every accepted change (resave, card edit, transition);
// Card.Version always equals the record version.
type ApplicationRecord struct {
	ID          string             `json:"id"`
	SessionID   string             `json:"session_id"`
	Version     int                `json:"version"`
	Demo        bool               `json:"demo"`
	Status      ReviewStatus       `json:"status"`
	Reason      ReasonCode         `json:"reason,omitempty"`
	Comment     string             `json:"comment,omitempty"`
	CreatedAt   time.Time          `json:"created_at"`
	UpdatedAt   time.Time          `json:"updated_at"`
	Form        domain.Application `json:"form"`
	Card        NeedCard           `json:"card"`
	PrevCards   []NeedCard         `json:"previous_cards"` // full history of earlier versions
	Changes     []Change           `json:"changes"`
	Transitions []TransitionEntry  `json:"transitions"`
	// RequestIDs remembers recent client_request_id values -> resulting version,
	// so a retried call returns the same outcome instead of applying twice.
	RequestIDs map[string]int `json:"request_ids,omitempty"`
}

const maxRememberedRequests = 200

func (r *ApplicationRecord) remember(requestID string) {
	if requestID == "" {
		return
	}
	if r.RequestIDs == nil {
		r.RequestIDs = map[string]int{}
	}
	if len(r.RequestIDs) >= maxRememberedRequests { // forget the request with the oldest version
		oldest, minVersion := "", int(^uint(0)>>1)
		for k, v := range r.RequestIDs {
			if v < minVersion || v == minVersion && k < oldest {
				oldest, minVersion = k, v
			}
		}
		delete(r.RequestIDs, oldest)
	}
	r.RequestIDs[requestID] = r.Version
}

func (r *ApplicationRecord) seen(requestID string) bool {
	_, ok := r.RequestIDs[requestID]
	return requestID != "" && ok
}

func clone(r ApplicationRecord) ApplicationRecord {
	out := r
	out.Card = cloneCard(r.Card)
	out.PrevCards = append([]NeedCard{}, r.PrevCards...)
	out.Changes = append([]Change{}, r.Changes...)
	out.Transitions = append([]TransitionEntry{}, r.Transitions...)
	out.RequestIDs = make(map[string]int, len(r.RequestIDs))
	for k, v := range r.RequestIDs {
		out.RequestIDs[k] = v
	}
	return out
}

func sameForm(a, b domain.Application) bool {
	return a.Phone == b.Phone && a.FullName == b.FullName && a.Company == b.Company && a.Summary == b.Summary
}

// SaveApplication creates the record on the first confirmed form and updates it on a resave.
// An identical resave is a no-op (no new version, no event). A changed form rebuilds the
// card from the current session, keeps the previous card in history and does not change
// the review status. Returns the record and the events to append.
func SaveApplication(existing *ApplicationRecord, session domain.Session, newID string, demo bool, now time.Time) (ApplicationRecord, []Event, error) {
	if session.Application == nil {
		return ApplicationRecord{}, nil, fmt.Errorf("session %s has no saved application form", session.ID)
	}
	form := *session.Application
	if existing == nil {
		card, err := BuildCard(session, newID, 1, demo, now)
		if err != nil {
			return ApplicationRecord{}, nil, err
		}
		rec := ApplicationRecord{ID: newID, SessionID: session.ID, Version: 1, Demo: demo, Status: StatusNew,
			CreatedAt: now.UTC(), UpdatedAt: now.UTC(), Form: form, Card: card,
			PrevCards: []NeedCard{}, Changes: []Change{}, Transitions: []TransitionEntry{}}
		return rec, []Event{applicationEvent(EventApplicationSaved, rec, now)}, nil
	}
	if existing.SessionID != session.ID {
		return *existing, nil, fmt.Errorf("application %s belongs to another session", existing.ID)
	}
	if sameForm(existing.Form, form) {
		return *existing, nil, nil
	}
	rec := clone(*existing)
	card, err := BuildCard(session, rec.ID, rec.Version+1, rec.Demo, now)
	if err != nil {
		return *existing, nil, err
	}
	rec.PrevCards = append(rec.PrevCards, existing.Card)
	rec.Version++
	rec.Form, rec.Card, rec.UpdatedAt = form, card, now.UTC()
	rec.Changes = append(rec.Changes, Change{Version: rec.Version, At: now.UTC(), Actor: ActorClient, Paths: []string{"form"}})
	return rec, []Event{applicationEvent(EventApplicationSaved, rec, now)}, nil
}

// EditCard applies card edits as a new record version. A retried requestID is a no-op.
func EditCard(rec ApplicationRecord, expectedVersion int, actor Actor, edits []Edit, requestID string, now time.Time) (ApplicationRecord, error) {
	if rec.seen(requestID) {
		return rec, nil
	}
	if rec.Status == StatusAccepted || rec.Status == StatusRejected {
		return rec, ErrApplicationClosed
	}
	if expectedVersion != rec.Version {
		return rec, ErrVersionConflict
	}
	card, change, err := ApplyEdits(rec.Card, rec.Version, actor, edits, now)
	if err != nil {
		return rec, err
	}
	out := clone(rec)
	out.PrevCards = append(out.PrevCards, rec.Card)
	out.Card, out.Version, out.UpdatedAt = card, card.Version, now.UTC()
	out.Changes = append(out.Changes, change)
	out.remember(requestID)
	return out, nil
}

// Transition moves the application between review states.
// - Retried requestID or a request for the status it already has: no-op, no event.
// - Stale expectedVersion: ErrVersionConflict.
func Transition(rec ApplicationRecord, action Action, reason ReasonCode, comment string, expectedVersion int,
	requestID string, now time.Time) (ApplicationRecord, []Event, error) {
	rule, ok := transitions[action]
	if !ok {
		return rec, nil, fmt.Errorf("%w: unknown action %q", ErrInvalidTransition, action)
	}
	if rec.seen(requestID) || rec.Status == rule.to && action != ActionReopen {
		return rec, nil, nil
	}
	if expectedVersion != rec.Version {
		return rec, nil, ErrVersionConflict
	}
	allowed := false
	for _, s := range rule.from {
		allowed = allowed || s == rec.Status
	}
	if !allowed {
		return rec, nil, fmt.Errorf("%w: %s from %s", ErrInvalidTransition, action, rec.Status)
	}
	comment = strings.TrimSpace(comment)
	if utf8.RuneCountInString(comment) > 1000 {
		return rec, nil, fmt.Errorf("%w: comment too long", ErrInvalidTransition)
	}
	if rule.needsReason {
		if _, ok := reasonCodes[reason]; !ok {
			return rec, nil, ErrReasonRequired
		}
	} else {
		reason, comment = "", ""
	}
	out := clone(rec)
	out.Version++
	out.Card.Version = out.Version
	entry := TransitionEntry{Version: out.Version, Action: action, From: rec.Status, To: rule.to,
		Reason: reason, Comment: comment, At: now.UTC(), RequestID: requestID}
	out.Status, out.Reason, out.Comment, out.UpdatedAt = rule.to, reason, comment, now.UTC()
	out.Transitions = append(out.Transitions, entry)
	out.remember(requestID)
	events := []Event{}
	switch rule.to {
	case StatusInReview:
		events = append(events, applicationEvent(EventReviewStarted, out, now))
	case StatusAccepted:
		events = append(events, applicationEvent(EventAccepted, out, now))
	case StatusNeedsInfo:
		e := applicationEvent(EventNeedsInfo, out, now)
		e.Reason = reason
		events = append(events, e)
	case StatusRejected:
		e := applicationEvent(EventRejected, out, now)
		e.Reason = reason
		events = append(events, e)
	}
	return out, events, nil
}

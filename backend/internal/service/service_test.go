package service

import (
	"context"
	"errors"
	"path/filepath"
	"testing"

	"energytool/backend/internal/domain"
	"energytool/backend/internal/store"
)

type fakeML struct {
	calls []domain.ConsultationRequest
	fn    func(domain.ConsultationRequest) (domain.ConsultationResult, error)
}

func (f *fakeML) Respond(_ context.Context, req domain.ConsultationRequest) (domain.ConsultationResult, error) {
	f.calls = append(f.calls, req)
	return f.fn(req)
}

func newTestService(t *testing.T, ml *fakeML) *Service {
	t.Helper()
	repository, err := store.NewFileStore(filepath.Join(t.TempDir(), "sessions.json"))
	if err != nil {
		t.Fatal(err)
	}
	return New(repository, ml)
}

func TestSessionIsolationAndCompleteHistory(t *testing.T) {
	ml := &fakeML{fn: func(req domain.ConsultationRequest) (domain.ConsultationResult, error) {
		return result(req.SessionID, "Ответ по базе знаний", domain.LeadState{SessionID: req.SessionID, Fields: map[string]string{}, Evidence: map[string]interface{}{}}), nil
	}}
	app := newTestService(t, ml)
	first, err := app.CreateSession()
	if err != nil {
		t.Fatal(err)
	}
	second, err := app.CreateSession()
	if err != nil {
		t.Fatal(err)
	}
	if _, err = app.SendMessage(context.Background(), first.ID, "Вопрос первый"); err != nil {
		t.Fatal(err)
	}
	if _, err = app.SendMessage(context.Background(), first.ID, "Вопрос второй"); err != nil {
		t.Fatal(err)
	}
	if _, err = app.SendMessage(context.Background(), second.ID, "Новый диалог"); err != nil {
		t.Fatal(err)
	}
	if got := len(ml.calls[1].Messages); got != 3 {
		t.Fatalf("second turn history length=%d, want 3", got)
	}
	if got := len(ml.calls[2].Messages); got != 1 {
		t.Fatalf("new session history length=%d, want 1", got)
	}
	if ml.calls[2].Lead != nil {
		t.Fatal("new session must begin with a null lead")
	}
	if ml.calls[2].SessionID != second.ID || ml.calls[2].Messages[0].Content != "Новый диалог" {
		t.Fatal("new session received foreign context")
	}
}

func TestLeadSurvivesTechnicalFailureAndSessionCanClose(t *testing.T) {
	call := 0
	ml := &fakeML{fn: func(req domain.ConsultationRequest) (domain.ConsultationResult, error) {
		call++
		if call == 1 {
			return result(req.SessionID, "Первый ответ", domain.LeadState{SessionID: req.SessionID, Fields: map[string]string{"company": "ООО Тест"}, Evidence: map[string]interface{}{}, Requested: true}), nil
		}
		return domain.ConsultationResult{}, errors.New("upstream error")
	}}
	app := newTestService(t, ml)
	session, err := app.CreateSession()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := app.SendMessage(context.Background(), session.ID, "Сохраните заявку"); err != nil {
		t.Fatal(err)
	}
	failure, err := app.SendMessage(context.Background(), session.ID, "Продолжение")
	if err != nil {
		t.Fatal(err)
	}
	if failure.Status != "technical_error" {
		t.Fatalf("status=%q", failure.Status)
	}
	if failure.Lead.Fields["company"] != "ООО Тест" {
		t.Fatal("technical failure erased lead")
	}
	closed, err := app.CloseSession(session.ID)
	if err != nil {
		t.Fatal(err)
	}
	if closed.Status != "closed" || closed.ClosedAt == nil {
		t.Fatal("session was not closed")
	}
	if _, err := app.SendMessage(context.Background(), session.ID, "после закрытия"); !errors.Is(err, ErrClosed) {
		t.Fatalf("send after close error=%v", err)
	}
	if len(closed.Messages) != 4 {
		t.Fatalf("history length=%d, want 4", len(closed.Messages))
	}
}

func TestHistoryLimitsAndEmptyMessage(t *testing.T) {
	ml := &fakeML{fn: func(req domain.ConsultationRequest) (domain.ConsultationResult, error) {
		return result(req.SessionID, "ok", domain.LeadState{SessionID: req.SessionID}), nil
	}}
	app := newTestService(t, ml)
	session, err := app.CreateSession()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := app.SendMessage(context.Background(), session.ID, " \n "); !errors.Is(err, ErrEmptyMessage) {
		t.Fatalf("empty message error=%v", err)
	}
	if _, err := app.SendMessage(context.Background(), session.ID, string(make([]rune, 10001))); err == nil {
		t.Fatal("oversized message accepted")
	}
	if len(ml.calls) != 0 {
		t.Fatal("invalid request called ML")
	}
}

func result(sessionID, answer string, lead domain.LeadState) domain.ConsultationResult {
	return domain.ConsultationResult{Answer: answer, Status: "answered", Sources: []map[string]interface{}{{"document_id": "kb/product.md", "chunk_id": "section-1", "source_id": "kb/product.md#section-1", "quote": "source quote"}}, ElapsedMS: 10, Lead: lead, Summary: map[string]interface{}{"sent": false}, Debug: map[string]interface{}{}, SchemaVersion: "1.0"}
}

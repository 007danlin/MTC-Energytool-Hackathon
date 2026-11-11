package service

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"energytool/backend/internal/consultation"
	"energytool/backend/internal/domain"
	"energytool/backend/internal/store"
)

var (
	ErrNotFound        = store.ErrNotFound
	ErrClosed          = errors.New("session is closed")
	ErrHistoryLimit    = errors.New("session history exceeds supported limit")
	ErrEmptyMessage    = errors.New("message must not be empty")
	ErrSessionConflict = errors.New("session changed while processing")
)

type Service struct {
	store store.Store
	ml    consultation.Client
	locks sync.Map
}

func New(s store.Store, ml consultation.Client) *Service { return &Service{store: s, ml: ml} }

func (s *Service) CreateSession() (domain.Session, error) {
	now := time.Now().UTC()
	id := newID()
	session := domain.Session{ID: id, Status: "active", CreatedAt: now, UpdatedAt: now,
		Messages: []domain.Message{}, Lead: domain.LeadState{SessionID: id,
			Fields: map[string]string{}, Evidence: map[string]interface{}{}}}
	if err := s.store.Create(session); err != nil {
		return domain.Session{}, err
	}
	return session, nil
}

func (s *Service) GetSession(id string) (domain.Session, error) { return s.store.Get(id) }
func (s *Service) ListSessions() ([]domain.Session, error)      { return s.store.List() }

func (s *Service) CloseSession(id string) (domain.Session, error) {
	unlock := s.lock(id)
	defer unlock()
	session, err := s.store.Get(id)
	if err != nil {
		return domain.Session{}, err
	}
	if session.Status != "closed" {
		now := time.Now().UTC()
		session.Status, session.ClosedAt, session.UpdatedAt = "closed", &now, now
		if err := s.store.Save(session); err != nil {
			return domain.Session{}, err
		}
	}
	return session, nil
}

func (s *Service) Lead(id string) (domain.LeadState, error) {
	session, err := s.store.Get(id)
	return session.Lead, err
}

func (s *Service) SendMessage(ctx context.Context, id, content string) (domain.ConsultationResult, error) {
	content = strings.TrimSpace(content)
	if content == "" {
		return domain.ConsultationResult{}, ErrEmptyMessage
	}
	if len([]rune(content)) > 10000 {
		return domain.ConsultationResult{}, errors.New("message exceeds 10000 characters")
	}
	unlock := s.lock(id)
	defer unlock()
	session, err := s.store.Get(id)
	if err != nil {
		return domain.ConsultationResult{}, err
	}
	if session.Status != "active" {
		return domain.ConsultationResult{}, ErrClosed
	}
	if len(session.Messages)+1 > 200 {
		return domain.ConsultationResult{}, ErrHistoryLimit
	}
	totalChars := len([]rune(content))
	for _, message := range session.Messages {
		totalChars += len([]rune(message.Content))
	}
	if totalChars > 100000 {
		return domain.ConsultationResult{}, ErrHistoryLimit
	}

	userMessage := domain.Message{ID: newID(), Role: "user", Content: content,
		Sequence: len(session.Messages) + 1, CreatedAt: time.Now().UTC()}
	session.Messages = append(session.Messages, userMessage)
	session.UpdatedAt = userMessage.CreatedAt
	if err := s.store.Save(session); err != nil {
		return domain.ConsultationResult{}, err
	}
	if s.ml == nil {
		return s.recordTechnicalFailure(session, errors.New("consultation service is not configured"))
	}
	mlRequest := domain.ConsultationRequest{SessionID: session.ID, Messages: make([]domain.MessageInput, 0, len(session.Messages))}
	if session.LastResult != nil {
		lead := session.Lead
		mlRequest.Lead = &lead
	}
	for _, message := range session.Messages {
		mlRequest.Messages = append(mlRequest.Messages, domain.MessageInput{Role: message.Role, Content: message.Content})
	}
	mlStarted := time.Now()
	result, err := s.ml.Respond(ctx, mlRequest)
	if err != nil {
		return s.recordTechnicalFailure(session, err)
	}
	if result.Debug == nil {
		result.Debug = map[string]interface{}{}
	}
	result.Debug["ml_elapsed_ms"] = result.ElapsedMS
	result.ElapsedMS = time.Since(mlStarted).Milliseconds()
	result.Debug["backend_elapsed_ms"] = result.ElapsedMS
	if result.Status == "technical_error" {
		// Keep prior successful lead and summary; the ML call must not erase state on failure.
		result.Lead = session.Lead
		if session.LastResult != nil {
			result.Summary = session.LastResult.Summary
		}
	}
	if result.Lead.SessionID != session.ID {
		return s.recordTechnicalFailure(session, errors.New("ML returned mismatched session id"))
	}
	assistant := domain.Message{ID: newID(), Role: "assistant", Content: result.Answer,
		Sequence: len(session.Messages) + 1, CreatedAt: time.Now().UTC()}
	session.Messages = append(session.Messages, assistant)
	session.UpdatedAt = assistant.CreatedAt
	session.Lead = result.Lead
	session.LastResult = &result
	if err := s.store.Save(session); err != nil {
		return domain.ConsultationResult{}, err
	}
	return result, nil
}

func (s *Service) recordTechnicalFailure(session domain.Session, cause error) (domain.ConsultationResult, error) {
	answer := "Сейчас не удалось получить ответ из-за технического сбоя. История диалога сохранена; попробуйте позже."
	result := domain.ConsultationResult{Answer: answer, Status: "technical_error", Sources: []map[string]interface{}{},
		ElapsedMS: 0, Lead: session.Lead, LeadReady: false, Summary: map[string]interface{}{},
		Debug: map[string]interface{}{"error_code": "consultation_unavailable"}, SchemaVersion: "1.0"}
	if session.LastResult != nil {
		result.Summary = session.LastResult.Summary
		result.LeadReady = session.LastResult.LeadReady
	}
	result.Debug["backend_elapsed_ms"] = result.ElapsedMS
	assistant := domain.Message{ID: newID(), Role: "assistant", Content: answer, Sequence: len(session.Messages) + 1, CreatedAt: time.Now().UTC()}
	session.Messages = append(session.Messages, assistant)
	session.UpdatedAt = assistant.CreatedAt
	// Avoid returning or logging the raw upstream error, which could contain private details.
	_ = cause
	if err := s.store.Save(session); err != nil {
		return domain.ConsultationResult{}, fmt.Errorf("save technical fallback result: %w", err)
	}
	return result, nil
}

func (s *Service) lock(id string) func() {
	value, _ := s.locks.LoadOrStore(id, &sync.Mutex{})
	mutex := value.(*sync.Mutex)
	mutex.Lock()
	return mutex.Unlock
}

func newID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return fmt.Sprintf("%d-%d", time.Now().UnixNano(), time.Now().Unix())
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

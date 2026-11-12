package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"time"

	"energytool/backend/internal/domain"
	"energytool/backend/internal/service"
	"energytool/backend/internal/store"
)

type SessionService interface {
	CreateSession() (domain.Session, error)
	SaveApplication(string, domain.Application) (domain.Session, error)
	GetSession(string) (domain.Session, error)
	ListSessions() ([]domain.Session, error)
	CloseSession(string) (domain.Session, error)
	Lead(string) (domain.LeadState, error)
	SendMessage(context.Context, string, string) (domain.ConsultationResult, error)
}

type Readiness func(context.Context) error

type Server struct {
	service SessionService
	ready   Readiness
	logger  *slog.Logger
	timeout time.Duration
}

func New(service SessionService, ready Readiness, logger *slog.Logger, requestTimeout time.Duration) *Server {
	if logger == nil {
		logger = slog.Default()
	}
	if requestTimeout <= 0 {
		requestTimeout = 100 * time.Second
	}
	return &Server{service: service, ready: ready, logger: logger, timeout: requestTimeout}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health/live", s.live)
	mux.HandleFunc("GET /health/ready", s.readiness)
	mux.HandleFunc("POST /api/v1/sessions", s.createSession)
	mux.HandleFunc("GET /api/v1/sessions", s.listSessions)
	mux.HandleFunc("GET /api/v1/sessions/{sessionID}", s.getSession)
	mux.HandleFunc("POST /api/v1/sessions/{sessionID}/close", s.closeSession)
	mux.HandleFunc("GET /api/v1/sessions/{sessionID}/messages", s.getMessages)
	mux.HandleFunc("POST /api/v1/sessions/{sessionID}/messages", s.postMessage)
	mux.HandleFunc("GET /api/v1/sessions/{sessionID}/lead", s.getLead)
	mux.HandleFunc("POST /api/v1/sessions/{sessionID}/application", s.saveApplication)
	return requestID(recoverer(s.logger, mux))
}

func (s *Server) live(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) readiness(w http.ResponseWriter, r *http.Request) {
	if s.ready != nil {
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()
		if err := s.ready(ctx); err != nil {
			writeError(w, r, http.StatusServiceUnavailable, "not_ready", "Required dependency is unavailable")
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (s *Server) createSession(w http.ResponseWriter, r *http.Request) {
	if !emptyBody(w, r) {
		return
	}
	session, err := s.service.CreateSession()
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, session)
}

func (s *Server) listSessions(w http.ResponseWriter, r *http.Request) {
	if !emptyBody(w, r) {
		return
	}
	sessions, err := s.service.ListSessions()
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"sessions": sessions})
}

func (s *Server) getSession(w http.ResponseWriter, r *http.Request) {
	if !emptyBody(w, r) {
		return
	}
	session, err := s.service.GetSession(r.PathValue("sessionID"))
	if err != nil {
		s.mapError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (s *Server) closeSession(w http.ResponseWriter, r *http.Request) {
	if !emptyBody(w, r) {
		return
	}
	session, err := s.service.CloseSession(r.PathValue("sessionID"))
	if err != nil {
		s.mapError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (s *Server) getMessages(w http.ResponseWriter, r *http.Request) {
	if !emptyBody(w, r) {
		return
	}
	session, err := s.service.GetSession(r.PathValue("sessionID"))
	if err != nil {
		s.mapError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"messages": session.Messages})
}

func (s *Server) postMessage(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, 32<<10)
	var payload struct {
		Content string `json:"content"`
	}
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		status, code, message := http.StatusBadRequest, "invalid_json", "Request body must be valid JSON"
		var maxErr *http.MaxBytesError
		if errors.As(err, &maxErr) {
			status, code, message = http.StatusRequestEntityTooLarge, "body_too_large", "Request body is too large"
		}
		writeError(w, r, status, code, message)
		return
	}
	if err := ensureEOF(decoder); err != nil {
		writeError(w, r, http.StatusBadRequest, "invalid_json", "Request must contain one JSON object")
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), s.timeout)
	defer cancel()
	result, err := s.service.SendMessage(ctx, r.PathValue("sessionID"), payload.Content)
	if err != nil {
		s.mapError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *Server) getLead(w http.ResponseWriter, r *http.Request) {
	if !emptyBody(w, r) {
		return
	}
	lead, err := s.service.Lead(r.PathValue("sessionID"))
	if err != nil {
		s.mapError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, lead)
}

func (s *Server) mapError(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, service.ErrInvalidApplication):
		writeError(w, r, http.StatusBadRequest, "invalid_application", "Укажите корректный телефон и краткое описание задачи.")
	case errors.Is(err, store.ErrNotFound):
		writeError(w, r, http.StatusNotFound, "not_found", "Session was not found")
	case errors.Is(err, service.ErrClosed):
		writeError(w, r, http.StatusConflict, "session_closed", "Session is closed")
	case errors.Is(err, service.ErrHistoryLimit):
		writeError(w, r, http.StatusRequestEntityTooLarge, "history_limit", "Session history limit reached")
	case errors.Is(err, service.ErrMessageTooLong):
		writeError(w, r, http.StatusRequestEntityTooLarge, "message_too_long", "Message exceeds 10000 characters")
	case errors.Is(err, service.ErrEmptyMessage):
		writeError(w, r, http.StatusBadRequest, "empty_message", "Message content is required")
	default:
		s.internalError(w, r, err)
	}
}

func (s *Server) internalError(w http.ResponseWriter, r *http.Request, err error) {
	s.logger.Error("backend request failed", "request_id", requestIDFrom(r.Context()), "error_type", fmt.Sprintf("%T", err))
	writeError(w, r, http.StatusInternalServerError, "internal_error", "Request could not be completed")
}

func emptyBody(w http.ResponseWriter, r *http.Request) bool {
	if r.Body == nil {
		return true
	}
	defer r.Body.Close()
	data, err := io.ReadAll(io.LimitReader(r.Body, 1))
	if err != nil || len(data) != 0 {
		writeError(w, r, http.StatusBadRequest, "unexpected_body", "This endpoint does not accept a body")
		return false
	}
	return true
}

func ensureEOF(decoder *json.Decoder) error {
	var extra interface{}
	if err := decoder.Decode(&extra); err != io.EOF {
		return errors.New("unexpected trailing JSON")
	}
	return nil
}

func writeJSON(w http.ResponseWriter, status int, value interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, r *http.Request, status int, code, message string) {
	writeJSON(w, status, domain.APIError{Code: code, Message: message, RequestID: requestIDFrom(r.Context())})
}

func (s *Server) saveApplication(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, 16<<10)
	var payload struct {
		FullName string `json:"full_name"`
		Phone    string `json:"phone"`
		Company  string `json:"company"`
		Summary  string `json:"summary"`
	}
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(w, r, http.StatusBadRequest, "invalid_json", "Некорректные данные заявки.")
		return
	}
	if err := ensureEOF(decoder); err != nil {
		writeError(w, r, http.StatusBadRequest, "invalid_json", "Некорректные данные заявки.")
		return
	}
	session, err := s.service.SaveApplication(r.PathValue("sessionID"), domain.Application{FullName: payload.FullName, Phone: payload.Phone, Company: payload.Company, Summary: payload.Summary})
	if err != nil {
		s.mapError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

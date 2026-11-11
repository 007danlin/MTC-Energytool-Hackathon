package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"energytool/backend/internal/domain"
	"energytool/backend/internal/service"
	"energytool/backend/internal/store"
)

type testML struct{}

func (testML) Respond(_ context.Context, req domain.ConsultationRequest) (domain.ConsultationResult, error) {
	return domain.ConsultationResult{Answer: "Уточните задачу.", Status: "clarification", Sources: []map[string]interface{}{}, Lead: domain.LeadState{SessionID: req.SessionID, Fields: map[string]string{}, Evidence: map[string]interface{}{}}, Summary: map[string]interface{}{"sent": false}, Debug: map[string]interface{}{}, SchemaVersion: "1.0"}, nil
}

func TestChatHTTPFlowAndErrorShape(t *testing.T) {
	repository, err := store.NewFileStore(t.TempDir() + "/sessions.json")
	if err != nil {
		t.Fatal(err)
	}
	app := service.New(repository, testML{})
	server := New(app, nil, nil, time.Second).Handler()
	created := httptest.NewRecorder()
	server.ServeHTTP(created, httptest.NewRequest(http.MethodPost, "/api/v1/sessions", nil))
	if created.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", created.Code, created.Body)
	}
	var session domain.Session
	if err := json.Unmarshal(created.Body.Bytes(), &session); err != nil {
		t.Fatal(err)
	}
	if session.ID == "" {
		t.Fatal("session ID missing")
	}
	response := httptest.NewRecorder()
	server.ServeHTTP(response, httptest.NewRequest(http.MethodPost, "/api/v1/sessions/"+session.ID+"/messages", strings.NewReader(`{"content":"Нужен учет энергопотребления"}`)))
	if response.Code != http.StatusOK {
		t.Fatalf("message status=%d body=%s", response.Code, response.Body)
	}
	if response.Header().Get("X-Request-ID") == "" {
		t.Fatal("request ID header missing")
	}
	var result domain.ConsultationResult
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.Answer != "Уточните задачу." || result.Sources == nil {
		t.Fatalf("result=%+v", result)
	}
	missing := httptest.NewRecorder()
	server.ServeHTTP(missing, httptest.NewRequest(http.MethodGet, "/api/v1/sessions/missing", nil))
	if missing.Code != http.StatusNotFound {
		t.Fatalf("missing status=%d", missing.Code)
	}
	var apiError domain.APIError
	if err := json.Unmarshal(missing.Body.Bytes(), &apiError); err != nil {
		t.Fatal(err)
	}
	if apiError.Code != "not_found" || apiError.RequestID == "" {
		t.Fatalf("error=%+v", apiError)
	}
}

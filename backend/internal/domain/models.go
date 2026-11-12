package domain

import "time"

type Application struct {
	FullName string    `json:"full_name"`
	Phone    string    `json:"phone"`
	Company  string    `json:"company"`
	Summary  string    `json:"summary"`
	SavedAt  time.Time `json:"saved_at"`
}

type Session struct {
	Application *Application        `json:"application,omitempty"`
	ID          string              `json:"id"`
	Status      string              `json:"status"`
	CreatedAt   time.Time           `json:"created_at"`
	UpdatedAt   time.Time           `json:"updated_at"`
	ClosedAt    *time.Time          `json:"closed_at,omitempty"`
	Messages    []Message           `json:"messages"`
	Lead        LeadState           `json:"lead"`
	LastResult  *ConsultationResult `json:"last_result,omitempty"`
}

type ResponseMeta struct {
	Status    string                   `json:"status"`
	Sources   []map[string]interface{} `json:"sources"`
	ElapsedMS int64                    `json:"elapsed_ms"`
}

type Message struct {
	Response  *ResponseMeta `json:"response,omitempty"`
	ID        string        `json:"id"`
	Role      string        `json:"role"`
	Content   string        `json:"content"`
	Sequence  int           `json:"sequence"`
	CreatedAt time.Time     `json:"created_at"`
}

type LeadState struct {
	SessionID string                 `json:"session_id"`
	Fields    map[string]string      `json:"fields"`
	Evidence  map[string]interface{} `json:"evidence"`
	Requested bool                   `json:"requested"`
	Declined  bool                   `json:"declined"`
}

type ConsultationRequest struct {
	SessionID string         `json:"session_id"`
	Messages  []MessageInput `json:"messages"`
	Lead      *LeadState     `json:"lead"`
}

type MessageInput struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ConsultationResult struct {
	Answer        string                   `json:"answer"`
	Status        string                   `json:"status"`
	Sources       []map[string]interface{} `json:"sources"`
	ElapsedMS     int64                    `json:"elapsed_ms"`
	Lead          LeadState                `json:"lead"`
	LeadReady     bool                     `json:"lead_ready"`
	Summary       map[string]interface{}   `json:"summary"`
	Debug         map[string]interface{}   `json:"debug"`
	SchemaVersion string                   `json:"schema_version"`
}

type APIError struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	RequestID string `json:"request_id"`
}

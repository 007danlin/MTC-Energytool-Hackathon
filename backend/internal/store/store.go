package store

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sync"
	"time"

	"energytool/backend/internal/domain"
	"energytool/backend/internal/expert"
)

var ErrNotFound = errors.New("session not found")

// Store persists the prototype state atomically in a private JSON file.
// The interface is intentionally small so a PostgreSQL implementation can replace it.
type Store interface {
	Create(domain.Session) error
	Get(string) (domain.Session, error)
	Save(domain.Session) error
	List() ([]domain.Session, error)
}

type ExpertStore interface {
	GetExpertRequest(string) (expert.Request, error)
	GetExpertRequestByKey(string, string) (*expert.Request, error)
	SaveExpertRequest(expert.Request, int) error
	ListExpertRequests(expert.RequestFilter) ([]expert.Request, error)
	GetKnowledge(string) (expert.KnowledgeEntry, error)
	SaveKnowledge(expert.KnowledgeEntry, int) error
	ListKnowledge() ([]expert.KnowledgeEntry, error)
	DeliverExpertReply(expert.Request, string, string) (expert.Request, error)
}

type FileStore struct {
	mu             sync.RWMutex
	path           string
	data           map[string]domain.Session
	expertRequests map[string]expert.Request
	knowledge      map[string]expert.KnowledgeEntry
}

func NewFileStore(path string) (*FileStore, error) {
	s := &FileStore{path: path, data: make(map[string]domain.Session), expertRequests: make(map[string]expert.Request), knowledge: make(map[string]expert.KnowledgeEntry)}
	if path == "" {
		return nil, errors.New("store path is required")
	}
	contents, err := os.ReadFile(path)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	if len(contents) > 0 {
		var envelope struct {
			Sessions       map[string]domain.Session        `json:"sessions"`
			ExpertRequests map[string]expert.Request        `json:"expert_requests"`
			Knowledge      map[string]expert.KnowledgeEntry `json:"knowledge_entries"`
		}
		if err := json.Unmarshal(contents, &envelope); err != nil {
			return nil, errors.New("decode session store")
		}
		if envelope.Sessions == nil {
			// Backward compatibility with the original sessions-only JSON format.
			if err := json.Unmarshal(contents, &s.data); err != nil {
				return nil, errors.New("decode session store")
			}
		} else {
			s.data, s.expertRequests, s.knowledge = envelope.Sessions, envelope.ExpertRequests, envelope.Knowledge
		}
		if s.data == nil {
			s.data = make(map[string]domain.Session)
		}
		if s.expertRequests == nil {
			s.expertRequests = make(map[string]expert.Request)
		}
		if s.knowledge == nil {
			s.knowledge = make(map[string]expert.KnowledgeEntry)
		}
	}
	return s, nil
}

func (s *FileStore) Create(session domain.Session) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.data[session.ID]; exists {
		return errors.New("session already exists")
	}
	s.data[session.ID] = session
	if err := s.persist(); err != nil {
		delete(s.data, session.ID)
		return err
	}
	return nil
}

func (s *FileStore) Get(id string) (domain.Session, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	session, ok := s.data[id]
	if !ok {
		return domain.Session{}, ErrNotFound
	}
	return clone(session)
}

func (s *FileStore) Save(session domain.Session) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	previous, ok := s.data[session.ID]
	if !ok {
		return ErrNotFound
	}
	s.data[session.ID] = session
	if err := s.persist(); err != nil {
		s.data[session.ID] = previous
		return err
	}
	return nil
}

func (s *FileStore) List() ([]domain.Session, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	result := make([]domain.Session, 0, len(s.data))
	for _, session := range s.data {
		copy, err := clone(session)
		if err != nil {
			return nil, err
		}
		result = append(result, copy)
	}
	return result, nil
}

func (s *FileStore) persist() error {
	if err := os.MkdirAll(filepath.Dir(s.path), 0700); err != nil {
		return err
	}
	data, err := json.Marshal(struct {
		Sessions       map[string]domain.Session        `json:"sessions"`
		ExpertRequests map[string]expert.Request        `json:"expert_requests"`
		Knowledge      map[string]expert.KnowledgeEntry `json:"knowledge_entries"`
	}{s.data, s.expertRequests, s.knowledge})
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(s.path), ".sessions-*.tmp")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName)
	if err := tmp.Chmod(0600); err != nil {
		tmp.Close()
		return err
	}
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmpName, s.path)
}

func (s *FileStore) GetExpertRequest(id string) (expert.Request, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	r, ok := s.expertRequests[id]
	if !ok {
		return expert.Request{}, ErrNotFound
	}
	return r, nil
}
func (s *FileStore) GetExpertRequestByKey(sessionID, originID string) (*expert.Request, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, r := range s.expertRequests {
		if r.SessionID == sessionID && r.OriginMessageID == originID {
			c := r
			return &c, nil
		}
	}
	return nil, nil
}
func (s *FileStore) SaveExpertRequest(r expert.Request, previous int) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	old, ok := s.expertRequests[r.ID]
	if previous == 0 && ok || previous != 0 && (!ok || old.Version != previous) {
		return expert.ErrVersionConflict
	}
	for _, x := range s.expertRequests {
		if x.ID != r.ID && x.SessionID == r.SessionID && x.OriginMessageID == r.OriginMessageID {
			return expert.ErrVersionConflict
		}
	}
	s.expertRequests[r.ID] = r
	return s.persist()
}
func (s *FileStore) ListExpertRequests(f expert.RequestFilter) ([]expert.Request, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := []expert.Request{}
	for _, r := range s.expertRequests {
		if (f.Status == "" || r.Status == f.Status) && (f.AssigneeID == "" || r.AssigneeID == f.AssigneeID) && (f.SessionID == "" || r.SessionID == f.SessionID) {
			out = append(out, r)
		}
	}
	return out, nil
}
func (s *FileStore) GetKnowledge(id string) (expert.KnowledgeEntry, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	e, ok := s.knowledge[id]
	if !ok {
		return expert.KnowledgeEntry{}, ErrNotFound
	}
	return e, nil
}
func (s *FileStore) SaveKnowledge(e expert.KnowledgeEntry, previous int) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	old, ok := s.knowledge[e.ID]
	if previous == 0 && ok || previous != 0 && (!ok || old.Version != previous) {
		return expert.ErrVersionConflict
	}
	s.knowledge[e.ID] = e
	return s.persist()
}
func (s *FileStore) ListKnowledge() ([]expert.KnowledgeEntry, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]expert.KnowledgeEntry, 0, len(s.knowledge))
	for _, e := range s.knowledge {
		out = append(out, e)
	}
	return out, nil
}

// DeliverExpertReply atomically appends the specialist answer to an active
// session and records delivery in the same durable JSON commit. Replays of the
// same reply ID are no-ops, including after a process restart.
func (s *FileStore) DeliverExpertReply(r expert.Request, replyID, sessionID string) (expert.Request, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	stored, ok := s.expertRequests[r.ID]
	if !ok || stored.Version != r.Version {
		return expert.Request{}, expert.ErrVersionConflict
	}
	session, ok := s.data[sessionID]
	if !ok {
		return expert.Request{}, ErrNotFound
	}
	previousSession, err := clone(session)
	if err != nil {
		return expert.Request{}, err
	}
	session = previousSession
	if stored.Reply == nil || stored.Reply.ID != replyID {
		return expert.Request{}, errors.New("expert reply is missing")
	}
	if stored.Reply.Delivery == expert.DeliveryDelivered {
		return stored, nil
	}
	if session.Status == "active" {
		alreadyInHistory := false
		for _, message := range session.Messages {
			if message.Response != nil && message.Response.Origin == "specialist" && message.Response.ReplyID == replyID {
				alreadyInHistory = true
				break
			}
		}
		if !alreadyInHistory {
			session.Messages = append(session.Messages, domain.Message{ID: "expert-" + replyID, Role: "assistant", Content: stored.Reply.Body, Sequence: len(session.Messages) + 1, CreatedAt: stored.Reply.CreatedAt, Response: &domain.ResponseMeta{Origin: "specialist", ReplyID: replyID, RequestID: stored.ID, Status: "expert_answer"}})
			session.UpdatedAt = time.Now().UTC()
		}
	}
	updated, err := expert.MarkDelivered(stored, expert.Actor{ID: "web-backend", Role: expert.RoleSystem}, expert.Command{ExpectedVersion: stored.Version, ID: "deliver-" + replyID}, replyID, session.Status != "active", time.Now())
	if err != nil {
		return stored, err
	}
	s.data[sessionID] = session
	s.expertRequests[updated.ID] = updated
	if err := s.persist(); err != nil {
		s.data[sessionID] = previousSession
		s.expertRequests[stored.ID] = stored
		return stored, err
	}
	return updated, nil
}

func clone(session domain.Session) (domain.Session, error) {
	data, err := json.Marshal(session)
	if err != nil {
		return domain.Session{}, err
	}
	var result domain.Session
	err = json.Unmarshal(data, &result)
	return result, err
}

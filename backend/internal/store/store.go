package store

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sync"

	"energytool/backend/internal/domain"
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

type FileStore struct {
	mu   sync.RWMutex
	path string
	data map[string]domain.Session
}

func NewFileStore(path string) (*FileStore, error) {
	s := &FileStore{path: path, data: make(map[string]domain.Session)}
	if path == "" {
		return nil, errors.New("store path is required")
	}
	contents, err := os.ReadFile(path)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	if len(contents) > 0 {
		if err := json.Unmarshal(contents, &s.data); err != nil {
			return nil, errors.New("decode session store")
		}
		if s.data == nil {
			s.data = make(map[string]domain.Session)
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
	data, err := json.Marshal(s.data)
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

func clone(session domain.Session) (domain.Session, error) {
	data, err := json.Marshal(session)
	if err != nil {
		return domain.Session{}, err
	}
	var result domain.Session
	err = json.Unmarshal(data, &result)
	return result, err
}

"""Precomputed BGE dense index with verified query space and exact lexical fallback."""
from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import urllib.request

from retrieval import LexicalRetriever
from settings import env_first

MODEL = 'BAAI/bge-m3'
ENCODING = {'pooling': 'cls', 'normalize': 'l2', 'prefix': '', 'max_tokens': 8192, 'dimension': 1024}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def rows_signature(fragments):
    return [[f.source_id, digest(f.text.encode('utf8'))] for f in fragments]

def unit(vector, dimension=1024):
    if not isinstance(vector, (list, tuple, array)) or len(vector) != dimension:
        raise ValueError('embedding_dimension')
    if any(type(x) is bool or not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector):
        raise ValueError('embedding_nonfinite')
    norm = math.sqrt(sum(x*x for x in vector))
    if norm < 1e-12:
        raise ValueError('embedding_zero')
    return [float(x)/norm for x in vector]

def dot(a, b):
    return sum(x*y for x,y in zip(a,b))

class EmbeddingAPI:
    def __init__(self, settings, model, deadline=None):
        self.settings, self.model, self.deadline = settings, model, deadline
        self.calls = 0

    def encode(self, texts, timeout=5):
        remaining = (self.deadline - time.monotonic() - 60) if self.deadline else timeout
        if remaining <= 0:
            raise ValueError('embedding_budget')
        body = json.dumps({'model': self.model, 'input': texts, 'encoding_format': 'float'}, ensure_ascii=False).encode()
        request = urllib.request.Request(self.settings.base_url.rstrip('/')+'/embeddings',data=body,
            headers={'Content-Type':'application/json','Authorization':'Bearer '+self.settings.api_key})
        self.calls += 1
        with urllib.request.urlopen(request, timeout=min(timeout,remaining)) as response:
            raw = response.read(8_000_001)
        if len(raw)>8_000_000:
            raise ValueError('embedding_response_size')
        payload=json.loads(raw)
        if payload.get('model',self.model)!=self.model:
            raise ValueError('embedding_response_model')
        data=payload.get('data')
        if not isinstance(data,list) or len(data)!=len(texts):
            raise ValueError('embedding_cardinality')
        indexed={}
        for row in data:
            i=row.get('index')
            if type(i) is not int or not 0<=i<len(texts) or i in indexed:
                raise ValueError('embedding_indices')
            indexed[i]=unit(row.get('embedding'))
        return [indexed[i] for i in range(len(texts))]

class HybridRetriever:
    def __init__(self, lexical, directory, client, model=MODEL, mode='hybrid', context_chars=32000):
        self.lexical,self.fragments,self.client=lexical,lexical.fragments,client
        self.mode=mode
        self.context_chars=context_chars
        self.status={'mode':'lexical','reason':'index_not_loaded'}
        self.lock=threading.Lock();self.cache={};self.checked=False;self.enabled=False
        try:
            if model!=MODEL:
                raise ValueError('embedding_model_mismatch')
            path=Path(directory)/'embedding_index.json'
            if path.stat().st_size>1_000_000:
                raise ValueError('index_metadata_size')
            manifest=json.loads(path.read_text(encoding='utf8'))
            if manifest.get('schema')!=1 or manifest.get('model')!=model or manifest.get('encoding')!=ENCODING:
                raise ValueError('index_contract_mismatch')
            if manifest.get('rows')!=rows_signature(self.fragments):
                raise ValueError('index_corpus_mismatch')
            probes=manifest.get('probes')
            if not isinstance(probes,list) or not 2<=len(probes)<=4 or any(not isinstance(x,str) or len(x)>20000 for x in probes):
                raise ValueError('index_probes')
            binary=Path(directory)/'embedding_vectors.bin'
            expected=(len(self.fragments)+len(probes))*1024*4
            if expected>64_000_000 or binary.stat().st_size!=expected:
                raise ValueError('index_vector_size')
            data=binary.read_bytes()
            if digest(data)!=manifest.get('vectors_sha256'):
                raise ValueError('index_checksum')
            values=array('f');values.frombytes(data)
            if sys.byteorder!='little':values.byteswap()
            matrix=[unit(values[i:i+1024]) for i in range(0,len(values),1024)]
            self.vectors=matrix[:len(self.fragments)];self.references=matrix[len(self.fragments):];self.probes=probes
            self.enabled=True;self.status={'mode':'pending','reason':'query_space_not_verified'}
        except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError):
            self.disable('index_or_model_invalid')

    def disable(self,reason):
        self.enabled=False;self.status={'mode':'lexical','reason':reason}

    def _vector(self, query):
        if len(query)>4096:
            raise ValueError('query_too_long')
        with self.lock:
            if not self.enabled:raise ValueError('index_disabled')
            if not self.checked:
                actual=self.client.encode(self.probes,timeout=10)
                if len(actual)!=len(self.references):raise ValueError('probe_count')
                cosines=[dot(unit(a),b) for a,b in zip(actual,self.references)]
                if min(cosines)<.999:
                    raise ValueError('query_space_mismatch')
                self.checked=True;self.status={'mode':self.mode,'reason':'verified_probes','probe_cosines':cosines}
            if query in self.cache:return self.cache[query]
        vector=unit(self.client.encode([query])[0])
        with self.lock:
            if len(self.cache)<512:self.cache[query]=vector
        return vector

    def search(self,query,top_k=12):
        if top_k<=0:return []
        baseline=self.lexical.search(query,top_k)
        if not self.enabled or len(query)>4096:return baseline
        try:
            vector=self._vector(query)
            dense=sorted(range(len(self.fragments)),key=lambda i:(-dot(vector,self.vectors[i]),self.fragments[i].source_id))
            # All original A2 candidates remain the unchanged prefix. Compute
            # the same accepted context as Consultant before spending spare space.
            used=0;accepted=set()
            for f in baseline:
                if f.source_id in accepted or not f.text.strip():continue
                if used+len(f.text)>self.context_chars:continue
                used+=len(f.text);accepted.add(f.source_id)
            # Expand only when at least two dense top-3 sections are missing
            # from the actual accepted A2 context. Otherwise keep exact A2.
            if sum(self.fragments[i].source_id not in accepted for i in dense[:3]) < 2:
                return baseline
            seen={f.source_id for f in baseline}
            out=list(baseline);added_chars=0;added_primary=0
            # Fixed conservative expansion: at most four new dense top-12
            # sections and their complete product safeguards, <=6000 chars.
            for i in dense[:12]:
                f=self.fragments[i]
                if f.source_id in seen:continue
                guards=[g for g in self.fragments if g.document_id==f.document_id
                        and any(t in g.text.split('\n',1)[0] for t in
                        ('Чего утверждать нельзя','Что нужно от клиента',
                         'Важное ограничение','Не подходит, если'))]
                if any(g.source_id in seen and g.source_id not in accepted for g in guards):
                    continue  # A guard rejected by the A2 context budget cannot be silently omitted.
                bundle=[];bundle_ids=set()
                for g in [f]+guards:
                    if g.source_id not in seen and g.source_id not in bundle_ids and g.text.strip():
                        bundle.append(g);bundle_ids.add(g.source_id)
                cost=sum(len(g.text) for g in bundle)
                if used+cost>self.context_chars or added_chars+cost>6000:continue
                out.extend(bundle);seen.update(bundle_ids);accepted.update(bundle_ids)
                used+=cost;added_chars+=cost;added_primary+=1
                if added_primary>=4:break
            return out
        except Exception:
            # Circuit breaker: never retry embedding failures on every question.
            with self.lock:self.disable('embedding_unavailable_or_incompatible')
            return baseline

def create_retriever(knowledge_path,settings,deadline=None):
    lexical=LexicalRetriever.from_zip(knowledge_path)
    model=env_first('EMB_MODEL',default=MODEL)
    return HybridRetriever(lexical,Path(__file__).resolve().parent,
                           EmbeddingAPI(settings,model,deadline),model=model,context_chars=settings.context_chars)

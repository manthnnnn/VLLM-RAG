from typing import List, Dict, Any, Optional
import re
from uuid import uuid4

class RecursiveCharacterChunker:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = ["\n\n", "\n", ".", " ", ""]

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        final_chunks = []
        if not separators:
            # Fallback to character splitting
            for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
                final_chunks.append(text[i : i + self.chunk_size])
            return final_chunks

        separator = separators[0]
        new_separators = separators[1:]
        
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)

        current_chunk = ""
        for split in splits:
            if not split:
                continue
                
            if len(split) > self.chunk_size:
                if current_chunk:
                    final_chunks.append(current_chunk)
                    current_chunk = ""
                final_chunks.extend(self._split_text(split, new_separators))
            else:
                addition = split + (separator if separator else "")
                if len(current_chunk) + len(addition) <= self.chunk_size:
                    current_chunk += addition
                else:
                    if current_chunk:
                        final_chunks.append(current_chunk)
                    current_chunk = addition
                    
        if current_chunk:
            final_chunks.append(current_chunk)
            
        return [c.strip() for c in final_chunks if c.strip()]

    async def chunk_document(self, text: str, document_id: str, metadata: Dict[str, Any], page_number: Optional[int] = None) -> List[Dict[str, Any]]:
        raw_chunks = self._split_text(text, self.separators)
        
        chunks = []
        for idx, chunk_text in enumerate(raw_chunks):
            chunk_metadata = metadata.copy()
            chunk_metadata.update({
                "document_id": document_id,
                "chunk_index": idx,
                "page_number": page_number,
                "text": chunk_text
            })
            chunks.append({
                "chunk_id": str(uuid4()),
                "text": chunk_text,
                "metadata": chunk_metadata
            })
            
        return chunks

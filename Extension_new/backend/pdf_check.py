"""Bounded PDF extraction. Never follows URLs or retains uploaded documents."""
from io import BytesIO
import re
from fastapi import APIRouter, File, HTTPException, UploadFile
from pypdf import PdfReader
from starlette.concurrency import run_in_threadpool

router = APIRouter()
MAX_BYTES = 12 * 1024 * 1024

def extract_pdf(data: bytes) -> dict:
    if not data.startswith(b'%PDF-'): raise ValueError('Choose a valid PDF document.')
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted: raise ValueError('Password-protected PDFs are not supported.')
    if len(reader.pages) > 100: raise ValueError('Use a PDF with at most 100 pages.')
    text, links, seen = [], [], set()
    characters = 0
    truncated = False
    def add(url, page, source):
        nonlocal truncated
        if not isinstance(url, str) or not url.lower().startswith(('https://', 'http://')): return
        if url in seen: return
        if len(links) >= 200: truncated = True; return
        seen.add(url); links.append({'url': url[:4096], 'page': page, 'source': source})
    for number, page in enumerate(reader.pages, 1):
        body = page.extract_text() or ''
        if characters + len(body) > 100000: truncated = True
        remaining = max(0, 100000 - characters)
        text.append(body[:remaining]); characters += min(len(body), remaining)
        for match in re.findall(r'https?://[^\s<>"\)]+', body): add(match.rstrip('.,;'), number, 'text')
        for ref in page.get('/Annots', []):
            annotation = ref.get_object()
            action = annotation.get('/A')
            if action:
                action = action.get_object()
                if action.get('/S') == '/URI': add(action.get('/URI'), number, 'embedded link')
    combined = '\n'.join(text)
    return {'pages': len(reader.pages), 'text': combined, 'links': links, 'truncated': truncated,
            'image_only': not bool(combined.strip()), 'coverage': 'PDF text and HTTP/HTTPS links; no OCR, attachments, JavaScript or destination downloads.'}

@router.post('/api/analyze/pdf')
async def analyze_pdf(file: UploadFile = File(...)):
    try:
        data = await file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES: raise HTTPException(413, 'Use a PDF smaller than 12 MB.')
        return await run_in_threadpool(extract_pdf, data)
    except HTTPException: raise
    except Exception as error:
        raise HTTPException(422, str(error) if isinstance(error, ValueError) else 'Could not read this PDF.') from error
    finally: await file.close()

#!/usr/bin/env python3
"""
Mexican Health Sources Ingestion Pipeline for Ominis Health LLM
Ingests various Mexican health-related sources: PRONAM, NOMs, SSA documents, etc.
"""

import os
import sys
import json
import requests
import re
import tempfile
import hashlib
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse, unquote
import logging
import argparse
from dataclasses import dataclass, asdict

from bs4 import BeautifulSoup
import html2text

# PDF extraction
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("Warning: PyMuPDF not installed. PDF extraction will be disabled.")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SourceConfig:
    """Configuration for a data source"""
    name: str
    institution: str
    source_type: str
    url: str
    category: str = ""


# Define all sources
SOURCES = [
    SourceConfig(
        name="Protocolos Nacionales de Atención Médica (PRONAM)",
        institution="Consejo de Salubridad General / SSA",
        source_type="Protocolos Clínicos",
        url="https://pronamsalud.csg.gob.mx/",
        category="Protocolos Clínicos"
    ),
    SourceConfig(
        name="Protocolos PRONAM individuales (PDF)",
        institution="Consejo de Salubridad General / DOF",
        source_type="Protocolos Clínicos PDF",
        url="https://www.dof.gob.mx/2025/CSG/PRONAM_Linfoma_de_Hodgkin_en_ninas_ninos_y_adolescentes.pdf",
        category="Protocolos Clínicos"
    ),
    SourceConfig(
        name="Normas Oficiales Mexicanas (COFEPRIS)",
        institution="COFEPRIS",
        source_type="Normatividad Sanitaria",
        url="https://www.gob.mx/cofepris/acciones-y-programas/normas-oficiales-mexicana",
        category="Normatividad"
    ),
    SourceConfig(
        name="Compendio de Normas Oficiales Mexicanas (PDF)",
        institution="SSA / CENETEC",
        source_type="Normatividad Sanitaria",
        url="https://www.gob.mx/cms/uploads/attachment/file/802730/Compendio_Normas_Oficiales_Mexicanas.pdf",
        category="Normatividad"
    ),
    SourceConfig(
        name="NOM SSA (documentos oficiales)",
        institution="Secretaría de Salud",
        source_type="Normatividad",
        url="https://www.gob.mx/salud/en/documentos/normas-oficiales-mexicanas-9705",
        category="Normatividad"
    ),
    SourceConfig(
        name="Datos Abiertos Epidemiológicos (DGE)",
        institution="Secretaría de Salud / DGE",
        source_type="Datos Epidemiológicos",
        url="https://www.gob.mx/salud/documentos/datos-abiertos-152127",
        category="Datos Epidemiológicos"
    ),
    SourceConfig(
        name="Portal de Datos Abiertos - Salud",
        institution="Gobierno de México",
        source_type="Datos Abiertos",
        url="https://historico.datos.gob.mx/busca/organization/salud",
        category="Datos Abiertos"
    ),
    SourceConfig(
        name="Boletín Epidemiológico Semanal",
        institution="Secretaría de Salud / Epidemiología",
        source_type="Estadísticas de Salud",
        url="https://www.gob.mx/salud/acciones-y-programas/direccion-general-de-epidemiologia-boletin-epidemiologico",
        category="Epidemiología"
    ),
    SourceConfig(
        name="Manuales y Documentos Relevantes",
        institution="Secretaría de Salud",
        source_type="Manuales Técnicos",
        url="https://www.gob.mx/salud/documentos/manuales-y-documentos-relevantes",
        category="Manuales"
    ),
    SourceConfig(
        name="Manual de Organización SSA",
        institution="Secretaría de Salud",
        source_type="Lineamientos Institucionales",
        url="https://www.dgrh.salud.gob.mx/Manual_Organizacion.php",
        category="Lineamientos"
    ),
    SourceConfig(
        name="Acuerdos y Lineamientos DOF",
        institution="Secretaría de Salud",
        source_type="Lineamientos Oficiales",
        url="https://www.gob.mx/salud/acciones-y-programas/acuerdos-criterios-y-lineamientos-publicados-en-el-dof",
        category="Lineamientos"
    ),
    SourceConfig(
        name="Normatividad DGIS",
        institution="DGIsalud",
        source_type="Normatividad",
        url="https://www.dgis.salud.gob.mx/contenidos/normatividad/normatividad_gobmx.html",
        category="Normatividad"
    ),
    SourceConfig(
        name="Repositorio de Publicaciones (Centro de Documentación)",
        institution="Secretaría de Salud",
        source_type="Repositorio Documental",
        url="https://www.salud.gob.mx/unidades/cdi/bases.html",
        category="Repositorio"
    ),
]


class FileDownloader:
    """Download and cache files"""
    
    def __init__(self, cache_dir: str = None, verify_ssl: bool = True):
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), 'ominis_sources_cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Ominis-Health-Bot/1.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-MX,es;q=0.9,en;q=0.8',
        })
        
        # Disable SSL warnings if not verifying
        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def download_file(self, url: str, timeout: int = 120) -> Optional[str]:
        """Download file to cache and return local path"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        ext = os.path.splitext(urlparse(url).path)[1] or '.bin'
        cache_path = os.path.join(self.cache_dir, f"{url_hash}{ext}")
        
        if os.path.exists(cache_path):
            logger.debug(f"Using cached file: {cache_path}")
            return cache_path
        
        try:
            logger.info(f"Downloading: {url[:80]}...")
            response = self.session.get(url, timeout=timeout, stream=True, verify=self.verify_ssl)
            response.raise_for_status()
            
            with open(cache_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return cache_path
        except requests.exceptions.SSLError as e:
            # Retry without SSL verification
            logger.warning(f"SSL error, retrying without verification: {url}")
            try:
                response = self.session.get(url, timeout=timeout, stream=True, verify=False)
                response.raise_for_status()
                
                with open(cache_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return cache_path
            except Exception as e2:
                logger.error(f"Failed to download {url}: {e2}")
                return None
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return None
    
    def fetch_page(self, url: str, timeout: int = 30) -> Optional[BeautifulSoup]:
        """Fetch HTML page"""
        try:
            response = self.session.get(url, timeout=timeout, verify=self.verify_ssl)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.exceptions.SSLError as e:
            # Retry without SSL verification
            logger.warning(f"SSL error, retrying without verification: {url}")
            try:
                response = self.session.get(url, timeout=timeout, verify=False)
                response.raise_for_status()
                return BeautifulSoup(response.text, 'html.parser')
            except Exception as e2:
                logger.error(f"Failed to fetch {url}: {e2}")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None


class PDFExtractor:
    """Extract text from PDF files"""
    
    @staticmethod
    def extract_text(pdf_path: str, max_pages: int = 200) -> str:
        """Extract text from PDF file"""
        if not HAS_PYMUPDF:
            return ""
        
        try:
            doc = fitz.open(pdf_path)
            text_parts = []
            
            for page_num in range(min(len(doc), max_pages)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    text_parts.append(f"--- Página {page_num + 1} ---\n{text}")
            
            doc.close()
            return '\n\n'.join(text_parts)
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            return ""


class MexicanHealthSourcesIngestion:
    """Ingest Mexican health sources"""
    
    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data', 'mexican_health_sources'
        )
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.downloader = FileDownloader(verify_ssl=False)  # Some govt sites have SSL issues
        self.pdf_extractor = PDFExtractor()
        
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = True
        self.h2t.body_width = 0
        
        self.documents = []
    
    def generate_doc_id(self, source_name: str, title: str, index: int = 0) -> str:
        """Generate unique document ID"""
        slug = re.sub(r'[^a-z0-9]', '-', source_name.lower())[:30]
        title_slug = re.sub(r'[^a-z0-9]', '-', title.lower())[:30]
        return f"mxhealth-{slug}-{title_slug}-{index:03d}"
    
    def create_document(
        self,
        source: SourceConfig,
        title: str,
        content: str,
        url: str,
        pdf_url: str = None,
        extra_metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create a document dictionary"""
        doc_id = self.generate_doc_id(source.name, title, len(self.documents))
        
        doc = {
            'id': doc_id,
            'title': title,
            'content': content,
            'url': url,
            'pdf_url': pdf_url,
            'source': source.name,
            'category': source.category,
            'has_pdf_content': pdf_url is not None and len(content) > 500,
            'metadata': {
                'institution': source.institution,
                'source_type': source.source_type,
                'country': 'Mexico',
                'language': 'es',
                **(extra_metadata or {})
            },
            'ingested_at': datetime.now(timezone.utc).isoformat()
        }
        
        return doc
    
    def save_document(self, doc: Dict[str, Any]):
        """Save document to JSON file"""
        filepath = os.path.join(self.output_dir, f"{doc['id']}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(doc, ensure_ascii=False, indent=2, fp=f)
        self.documents.append(doc)
    
    def ingest_pronam_portal(self, source: SourceConfig) -> List[Dict[str, Any]]:
        """Ingest PRONAM protocols portal"""
        logger.info(f"Ingesting: {source.name}")
        docs = []
        
        soup = self.downloader.fetch_page(source.url)
        if not soup:
            return docs
        
        # Look for protocol links
        protocol_links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Look for PDF links or protocol pages
            if '.pdf' in href.lower() or 'protocolo' in text.lower() or 'pronam' in href.lower():
                full_url = urljoin(source.url, href)
                protocol_links.append((text, full_url))
        
        logger.info(f"Found {len(protocol_links)} protocol links")
        
        for title, url in protocol_links[:50]:  # Limit to 50
            if '.pdf' in url.lower():
                # Download and extract PDF
                pdf_path = self.downloader.download_file(url)
                if pdf_path:
                    content = self.pdf_extractor.extract_text(pdf_path)
                    if content:
                        doc = self.create_document(
                            source, title or "Protocolo PRONAM", content, 
                            source.url, pdf_url=url
                        )
                        self.save_document(doc)
                        docs.append(doc)
            else:
                # Fetch the page
                page_soup = self.downloader.fetch_page(url)
                if page_soup:
                    content = self.h2t.handle(str(page_soup.find('main') or page_soup.find('article') or page_soup.find('body')))
                    if content and len(content) > 100:
                        doc = self.create_document(source, title, content, url)
                        self.save_document(doc)
                        docs.append(doc)
            
            time.sleep(0.5)
        
        return docs
    
    def ingest_direct_pdf(self, source: SourceConfig) -> List[Dict[str, Any]]:
        """Ingest a direct PDF URL"""
        logger.info(f"Ingesting PDF: {source.name}")
        docs = []
        
        pdf_path = self.downloader.download_file(source.url)
        if pdf_path:
            content = self.pdf_extractor.extract_text(pdf_path)
            if content:
                # Extract title from filename or content
                filename = os.path.basename(urlparse(source.url).path)
                title = unquote(filename).replace('_', ' ').replace('.pdf', '')
                
                doc = self.create_document(
                    source, title or source.name, content,
                    source.url, pdf_url=source.url
                )
                self.save_document(doc)
                docs.append(doc)
        
        return docs
    
    def ingest_gob_mx_documents(self, source: SourceConfig) -> List[Dict[str, Any]]:
        """Ingest documents from gob.mx pages"""
        logger.info(f"Ingesting: {source.name}")
        docs = []
        
        soup = self.downloader.fetch_page(source.url)
        if not soup:
            return docs
        
        # Find all document links (PDFs, etc.)
        pdf_links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if '.pdf' in href.lower():
                full_url = urljoin(source.url, href)
                pdf_links.append((text, full_url))
        
        logger.info(f"Found {len(pdf_links)} PDF links")
        
        # Also extract page content as a document
        main_content = soup.find('article') or soup.find('main') or soup.find('div', class_='article-body')
        if main_content:
            page_content = self.h2t.handle(str(main_content))
            if page_content and len(page_content) > 200:
                doc = self.create_document(
                    source, source.name, page_content, source.url
                )
                self.save_document(doc)
                docs.append(doc)
        
        # Download PDFs
        for title, url in pdf_links[:30]:  # Limit
            pdf_path = self.downloader.download_file(url)
            if pdf_path:
                content = self.pdf_extractor.extract_text(pdf_path)
                if content and len(content) > 100:
                    doc = self.create_document(
                        source, title or "Documento", content,
                        source.url, pdf_url=url
                    )
                    self.save_document(doc)
                    docs.append(doc)
            time.sleep(0.3)
        
        return docs
    
    def ingest_dgis_normatividad(self, source: SourceConfig) -> List[Dict[str, Any]]:
        """Ingest DGIS normatividad page"""
        logger.info(f"Ingesting: {source.name}")
        docs = []
        
        soup = self.downloader.fetch_page(source.url)
        if not soup:
            return docs
        
        # Find links to norms and documents
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if '.pdf' in href.lower():
                full_url = urljoin(source.url, href)
                pdf_path = self.downloader.download_file(full_url)
                if pdf_path:
                    content = self.pdf_extractor.extract_text(pdf_path)
                    if content:
                        doc = self.create_document(
                            source, text or "Normatividad DGIS", content,
                            source.url, pdf_url=full_url
                        )
                        self.save_document(doc)
                        docs.append(doc)
                time.sleep(0.3)
        
        # Also get page content
        main_content = soup.find('div', class_='content') or soup.find('main') or soup.find('body')
        if main_content:
            page_content = self.h2t.handle(str(main_content))
            if page_content and len(page_content) > 200:
                doc = self.create_document(source, source.name, page_content, source.url)
                self.save_document(doc)
                docs.append(doc)
        
        return docs
    
    def ingest_salud_repository(self, source: SourceConfig) -> List[Dict[str, Any]]:
        """Ingest Salud documentation repository"""
        logger.info(f"Ingesting: {source.name}")
        docs = []
        
        soup = self.downloader.fetch_page(source.url)
        if not soup:
            return docs
        
        # Find all links to documents
        doc_links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if any(ext in href.lower() for ext in ['.pdf', '.doc', '.xls', '.htm']):
                full_url = urljoin(source.url, href)
                doc_links.append((text, full_url))
        
        logger.info(f"Found {len(doc_links)} document links")
        
        for title, url in doc_links[:50]:
            if '.pdf' in url.lower():
                pdf_path = self.downloader.download_file(url)
                if pdf_path:
                    content = self.pdf_extractor.extract_text(pdf_path)
                    if content:
                        doc = self.create_document(
                            source, title or "Documento CDI", content,
                            source.url, pdf_url=url
                        )
                        self.save_document(doc)
                        docs.append(doc)
            elif '.htm' in url.lower():
                page_soup = self.downloader.fetch_page(url)
                if page_soup:
                    content = self.h2t.handle(str(page_soup.find('body') or ''))
                    if content and len(content) > 100:
                        doc = self.create_document(source, title, content, url)
                        self.save_document(doc)
                        docs.append(doc)
            
            time.sleep(0.3)
        
        return docs
    
    def ingest_datos_abiertos(self, source: SourceConfig) -> List[Dict[str, Any]]:
        """Ingest open data sources (metadata about datasets)"""
        logger.info(f"Ingesting: {source.name}")
        docs = []
        
        soup = self.downloader.fetch_page(source.url)
        if not soup:
            return docs
        
        # Extract page content describing available datasets
        main_content = soup.find('article') or soup.find('main') or soup.find('div', class_='content')
        if main_content:
            page_content = self.h2t.handle(str(main_content))
            if page_content:
                doc = self.create_document(source, source.name, page_content, source.url)
                self.save_document(doc)
                docs.append(doc)
        
        # Look for dataset links
        dataset_links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if any(ext in href.lower() for ext in ['.csv', '.xlsx', '.json', '.pdf']):
                full_url = urljoin(source.url, href)
                dataset_links.append((text, full_url, href.split('.')[-1].lower()))
        
        logger.info(f"Found {len(dataset_links)} dataset links")
        
        # For now, just document the datasets available (actual data parsing would be complex)
        for title, url, ext in dataset_links[:20]:
            if ext == 'pdf':
                pdf_path = self.downloader.download_file(url)
                if pdf_path:
                    content = self.pdf_extractor.extract_text(pdf_path)
                    if content:
                        doc = self.create_document(
                            source, title or "Dataset", content,
                            source.url, pdf_url=url
                        )
                        self.save_document(doc)
                        docs.append(doc)
            time.sleep(0.3)
        
        return docs
    
    def ingest_source(self, source: SourceConfig) -> List[Dict[str, Any]]:
        """Ingest a single source based on its type"""
        url = source.url.lower()
        
        # Direct PDF
        if url.endswith('.pdf'):
            return self.ingest_direct_pdf(source)
        
        # PRONAM portal
        if 'pronamsalud' in url:
            return self.ingest_pronam_portal(source)
        
        # DGIS
        if 'dgis.salud' in url:
            return self.ingest_dgis_normatividad(source)
        
        # Salud repository
        if 'salud.gob.mx/unidades/cdi' in url:
            return self.ingest_salud_repository(source)
        
        # Datos abiertos
        if 'datos.gob.mx' in url or 'datos-abiertos' in url:
            return self.ingest_datos_abiertos(source)
        
        # Default: gob.mx document pages
        return self.ingest_gob_mx_documents(source)
    
    def ingest_all(self, sources: List[SourceConfig] = None) -> Dict[str, Any]:
        """Ingest all sources"""
        sources = sources or SOURCES
        
        summary = {
            'started_at': datetime.now(timezone.utc).isoformat(),
            'sources': {},
            'total_documents': 0,
            'total_with_pdf': 0
        }
        
        for source in sources:
            try:
                logger.info(f"\n{'='*60}")
                logger.info(f"Processing: {source.name}")
                logger.info(f"URL: {source.url}")
                logger.info(f"{'='*60}")
                
                docs = self.ingest_source(source)
                
                pdf_count = sum(1 for d in docs if d.get('has_pdf_content'))
                summary['sources'][source.name] = {
                    'institution': source.institution,
                    'url': source.url,
                    'documents': len(docs),
                    'with_pdf': pdf_count
                }
                
                logger.info(f"Ingested {len(docs)} documents ({pdf_count} with PDF content)")
                
            except Exception as e:
                logger.error(f"Error processing {source.name}: {e}")
                summary['sources'][source.name] = {'error': str(e)}
        
        summary['completed_at'] = datetime.now(timezone.utc).isoformat()
        summary['total_documents'] = len(self.documents)
        summary['total_with_pdf'] = sum(1 for d in self.documents if d.get('has_pdf_content'))
        
        # Save manifest
        manifest = {
            'created_at': datetime.now(timezone.utc).isoformat(),
            'document_count': len(self.documents),
            'sources': list(set(d['source'] for d in self.documents)),
            'documents': [
                {
                    'id': d['id'],
                    'title': d['title'],
                    'source': d['source'],
                    'has_pdf_content': d.get('has_pdf_content', False)
                }
                for d in self.documents
            ]
        }
        
        manifest_path = os.path.join(self.output_dir, 'manifest.json')
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, ensure_ascii=False, indent=2, fp=f)
        
        summary_path = os.path.join(self.output_dir, 'ingestion_summary.json')
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, ensure_ascii=False, indent=2, fp=f)
        
        return summary


def main():
    parser = argparse.ArgumentParser(description='Ingest Mexican Health Sources')
    parser.add_argument('--output-dir', help='Output directory')
    parser.add_argument('--source', help='Specific source name to ingest')
    parser.add_argument('--list-sources', action='store_true', help='List available sources')
    
    args = parser.parse_args()
    
    if args.list_sources:
        print("\nAvailable sources:")
        for i, source in enumerate(SOURCES, 1):
            print(f"{i}. {source.name}")
            print(f"   Institution: {source.institution}")
            print(f"   URL: {source.url}")
            print()
        return
    
    ingestion = MexicanHealthSourcesIngestion(args.output_dir)
    
    if args.source:
        # Find specific source
        source = next((s for s in SOURCES if args.source.lower() in s.name.lower()), None)
        if not source:
            print(f"Source not found: {args.source}")
            sys.exit(1)
        sources = [source]
    else:
        sources = SOURCES
    
    summary = ingestion.ingest_all(sources)
    
    print("\n" + "=" * 60)
    print("INGESTION COMPLETE")
    print("=" * 60)
    print(f"Total documents: {summary['total_documents']}")
    print(f"Documents with PDF content: {summary['total_with_pdf']}")
    print(f"Output directory: {ingestion.output_dir}")
    print("\nBy source:")
    for name, info in summary['sources'].items():
        if 'error' in info:
            print(f"  - {name}: ERROR - {info['error']}")
        else:
            print(f"  - {name}: {info['documents']} docs ({info['with_pdf']} with PDF)")


if __name__ == '__main__':
    main()

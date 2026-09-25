"""Local, page-bounded OCR. No API credentials or network requests at runtime."""
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import re
import importlib.util
import sys
import threading
import pymupdf

ROOT=Path(__file__).resolve().parent
MAX_PAGES=20
LOCK=threading.Lock()


def _runtime():
    local=ROOT/'ocr_runtime'
    if local.is_dir() and str(local) not in sys.path:sys.path.append(str(local))


def model_path():
    name='ch_PP-OCRv5_rec_mobile_infer.onnx'
    local=ROOT/'.ocr_models'/name
    return local if local.is_file() else ROOT/'models'/name


def available():
    _runtime()
    return (importlib.util.find_spec('rapidocr_onnxruntime') is not None
            and importlib.util.find_spec('opencc') is not None
            and model_path().is_file())


@lru_cache(maxsize=1)
def _engine():
    if not available():raise RuntimeError('OCR 组件未就绪。请检查依赖与模型文件。')
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2,
        rec_model_path=str(model_path()))


@lru_cache(maxsize=1)
def _converter():
    _runtime()
    from opencc import OpenCC
    return OpenCC('t2s')


def normalize_text(text):
    text=_converter().convert(text)
    # Only remove whitespace between CJK characters, not between value columns.
    return re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])','',text)


@dataclass
class OCRPage:
    page_number: int
    words: list
    raw_text: str
    low_confidence_count: int=0

    def get_text(self,kind=None):
        if kind=='words':return self.words
        return '\n'.join(w[4] for w in self.words)


def parse_page_selection(value,page_count):
    if not value.strip():return []
    pages=set()
    for part in re.split(r'[,，\s]+',value.strip()):
        match=re.fullmatch(r'(\d+)(?:[-–](\d+))?',part)
        if not match:raise ValueError('页码格式示例：270-274,278-279。请使用 PDF 页码。')
        start=int(match[1]);end=int(match[2] or start)
        if start<1 or end<start or end>page_count:raise ValueError(f'页码必须在 1—{page_count} 之间，且起始页不大于结束页。')
        if end-start+1>MAX_PAGES:raise ValueError(f'一次最多识别 {MAX_PAGES} 页，请只选择财务报表页。')
        pages.update(range(start,end+1))
    if len(pages)>MAX_PAGES:raise ValueError(f'一次最多识别 {MAX_PAGES} 页。')
    return sorted(pages)


def _recognize(page,header=False):
    import numpy as np
    clip=pymupdf.Rect(0,0,page.rect.width,page.rect.height*.25) if header else page.rect
    scale=2 if header else 3
    pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),clip=clip,alpha=False,colorspace=pymupdf.csRGB)
    # OCR consumes BGR images; conversion also preserves colored financial text.
    img=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)[:,:,::-1].copy()
    with LOCK:result,_=_engine()(img,use_cls=False)
    return result or [],scale


def ocr_page(page,number):
    result,scale=_recognize(page)
    words=[];raw=[];low=0
    for box,text,score in result:
        raw.append(text)
        normalized=normalize_text(text)
        if re.fullmatch(r'[\[（(][\d, .]+[\]）)]',normalized):
            normalized='('+normalized[1:-1]+')'
        numeric=bool(re.fullmatch(r'[\d,.()（）\[\]−–—+%\-\s]+',normalized))
        if numeric and score<.90:
            normalized='OCR待核对';low+=1
        xs=[p[0]/scale for p in box];ys=[p[1]/scale for p in box]
        words.append((min(xs),min(ys),max(xs),max(ys),normalized,0,0,0))
    words.sort(key=lambda w:(round((w[1]+w[3])/2/3),w[0]))
    return OCRPage(number,words,'\n'.join(raw),low)


def _heading_kind(text):
    patterns={
        'income':r'(?:合并|综合)?(?:损益表|利润表|收益表|综合收益表)',
        'balance':r'(?:合并|综合)?(?:资产负债表|财务状况表)',
        'cash':r'(?:合并|综合)?现金流量表',
    }
    for line in text.splitlines():
        line=re.sub(r'\s+','',line)
        for kind,pattern in patterns.items():
            if re.fullmatch(pattern+r'(?:[（(]?续[）)]?)?',line):return kind
        if re.fullmatch(r'(?:Consolidated)?(?:IncomeStatement|StatementofProfitorLoss)',line,re.I):return 'income'
        if re.fullmatch(r'(?:Consolidated)?(?:BalanceSheet|StatementofFinancialPosition)',line,re.I):return 'balance'
        if re.fullmatch(r'(?:Consolidated)?(?:CashFlowStatement|StatementofCashFlows)',line,re.I):return 'cash'
    return None


def locate_pages(doc,progress=None):
    candidates=[]
    for i,page in enumerate(doc):
        text=page.get_text()
        numeric=len(re.findall(r'\d{1,3}(?:,\d{3})+',text))
        years=set(re.findall(r'(?<!\d)(20\d{2})(?!\d)',text))
        if len(text.strip())<80 or (numeric>=12 and len(years)>=2):candidates.append(i)
    # Bounded discovery prevents a long scanned report locking the app for hours.
    candidates=candidates[:160]
    found=[];kinds=set()
    for index,i in enumerate(candidates):
        if progress:progress(index/max(len(candidates),1),f'定位财务报表 · 正在查看 PDF 第 {i+1} 页')
        result,_=_recognize(doc[i],header=True)
        kind=_heading_kind('\n'.join(normalize_text(r[1]) for r in result))
        if kind:
            kinds.add(kind);found.extend(range(i+1,min(i+4,len(doc))+1))
        if len(kinds)==3:break
    found=sorted(set(found))
    if not found:raise ValueError('自动定位未找到报表标题。请预览目录，并手动填写财务报表的 PDF 页码。')
    if len(found)>MAX_PAGES:raise ValueError('候选页较多，请手动选择需要的财务报表页。')
    return found


def recognize_pdf(data,pages=None,progress=None):
    with pymupdf.open(stream=data,filetype='pdf') as doc:
        selected=pages or locate_pages(doc,progress)
        if len(selected)>MAX_PAGES or any(n<1 or n>len(doc) for n in selected):raise ValueError('OCR 页码超出范围。')
        output={}
        for i,n in enumerate(selected):
            if progress:progress(i/len(selected),f'识别 PDF 第 {n} 页 · {i+1}/{len(selected)}')
            output[n]=ocr_page(doc[n-1],n)
        if progress:progress(1.0,'文字识别完成')
        return output

"""One-time setup: installs optional local OCR, never sends report contents."""
from pathlib import Path
import hashlib
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parent
MODEL='ch_PP-OCRv5_rec_mobile_infer.onnx'
SHA256='5825fc7ebf84ae7a412be049820b4d86d77620f204a041697b0494669b1742c5'
URL='https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/onnx/PP-OCRv5/rec/'+MODEL


def main():
    subprocess.run([sys.executable,'-m','pip','install','--target',str(ROOT/'ocr_runtime'),
                    'rapidocr-onnxruntime==1.4.4','opencc-python-reimplemented==0.1.7'],check=True)
    folder=ROOT/'.ocr_models';folder.mkdir(exist_ok=True)
    target=folder/MODEL
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=SHA256:
        temporary=target.with_suffix('.download')
        urllib.request.urlretrieve(URL,temporary)
        if hashlib.sha256(temporary.read_bytes()).hexdigest()!=SHA256:
            temporary.unlink()
            raise RuntimeError('OCR model checksum mismatch; installation stopped.')
        temporary.replace(target)
    print('Local OCR ready. Restart the app if it is already running.')


if __name__=='__main__':main()

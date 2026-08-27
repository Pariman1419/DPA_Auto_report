import os
import pathlib
import subprocess
import urllib.request
import urllib.error

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from services.product_request_service import (
    read_product_request, list_product_requests, list_timepoints,
    list_timepoint_folders, get_generation_stats, list_lots, list_lots_registry,
    list_generation_history, get_history_record, delete_history_record,
    get_next_revision, save_generation_history, list_preview_images, list_preview_imc, list_preview_bond, list_preview_sem
)
from models.schemas import ProductRequestData, ProductRequestListItem, GenerateReportRequest
from services.report_generator import DPAReportGenerator, OUTPUT_DIR
from routers.auth import get_current_user

router = APIRouter(prefix="/api", tags=["Product Request"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/stats")
def get_dashboard_stats(_user=Depends(get_current_user)):
    return get_generation_stats()


@router.get("/history")
def get_history(_user=Depends(get_current_user)):
    return list_generation_history()


@router.get("/history/{record_id}/download")
def download_history_file(record_id: int, _user=Depends(get_current_user)):
    record = get_history_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    path = record.get("file_path", "")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(
        path=path,
        filename=record.get("file_name", os.path.basename(path)),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@router.delete("/history/{record_id}")
def delete_history(record_id: int, _user=Depends(get_current_user)):
    ok = delete_history_record(record_id, delete_file=True)
    if not ok:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"status": "deleted"}


@router.get("/product-requests", response_model=list[ProductRequestListItem])
def get_all_product_requests(_user=Depends(get_current_user)):
    return list_product_requests()


@router.get("/product-request/{pr_number}", response_model=ProductRequestData)
def get_product_request(pr_number: str, _user=Depends(get_current_user)):
    try:
        return read_product_request(pr_number)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read data: {e}")


@router.get("/download-report")
def download_report(path: str, _user=Depends(get_current_user)):
    """Download a generated report — path must be inside OUTPUT_DIR or auto_result mount."""
    safe_root   = pathlib.Path(OUTPUT_DIR).resolve()
    result_root = pathlib.Path(
        os.getenv("IMAGE_MOUNT_ROOT", os.getenv("IMAGE_WIN_ROOT", r"D:\Auto_detect\Result"))
    ).resolve()
    requested = _resolve_image_path(path).resolve()

    if not (requested.is_relative_to(safe_root) or requested.is_relative_to(result_root)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not requested.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(requested),
        filename=requested.name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@router.get("/product-request/{pr_number}/lots", response_model=list[str])
def get_product_request_lots(pr_number: str, _user=Depends(get_current_user)):
    return list_lots(pr_number)


@router.get("/product-request/{pr_number}/lots-registry")
def get_product_request_lots_registry(pr_number: str, _user=Depends(get_current_user)):
    return list_lots_registry(pr_number)


@router.get("/product-request/{pr_number}/timepoints", response_model=list[str])
def get_product_request_timepoints(pr_number: str, lot: str = None, _user=Depends(get_current_user)):
    return list_timepoints(pr_number, lot)


@router.get("/product-request/{pr_number}/{timepoint}/folders", response_model=list[dict])
def get_product_request_timepoint_folders(pr_number: str, timepoint: str, lot: str, _user=Depends(get_current_user)):
    return list_timepoint_folders(pr_number, timepoint, lot)


@router.get("/product-request/{pr_number}/{timepoint}/next-revision")
def get_pr_next_revision(pr_number: str, timepoint: str, _user=Depends(get_current_user)):
    return {"nextRevision": get_next_revision(pr_number, timepoint)}


@router.post("/generate-report")
def generate_dpa_report(req: GenerateReportRequest, _user=Depends(get_current_user)):
    """Trigger PPTX generation."""
    try:
        next_rev = get_next_revision(req.prNumber, req.timepoint)

        gen = DPAReportGenerator(req.prNumber, req.timepoint, req.lot, req.selectedSections, revision=next_rev)
        output_path, stats = gen.generate()

        from logger import get_logger as _gl
        _log = _gl("product_request")
        _log.info("Report generated — PR=%s Lot=%s TP=%s metadata=%s images=%d missing=%d file=%s",
                  req.prNumber, req.lot, req.timepoint,
                  stats['metadata_found'], stats['images_found'], stats['images_missing'],
                  os.path.basename(output_path))

        save_generation_history(
            pr_no=req.prNumber,
            lot=req.lot,
            revision=next_rev,
            timepoint=req.timepoint,
            user_id=req.userId,
            file_name=os.path.basename(output_path),
            file_path=output_path,
        )

        return {
            "status":     "success",
            "revision":   next_rev,
            "outputPath": output_path,
            "filename":   os.path.basename(output_path),
            "stats":      stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

@router.get("/bond-excel-path")
def get_bond_excel_path(pr_no: str, timepoint: str, lot: str, _user=Depends(get_current_user)):
    """Get the path to BOND_ABILITY_REPORT.xlsx for a specific lot."""
    from services.product_request_service import find_bond_ability_excel
    path = find_bond_ability_excel(pr_no, timepoint, lot)
    return {"path": path}

@router.get("/product-request/{pr_number}/{timepoint}/{lot}/preview-images")
def get_preview_images(pr_number: str, timepoint: str, lot: str, category: str, _user=Depends(get_current_user)):
    return list_preview_images(pr_number, timepoint, lot, category)

@router.get("/product-request/{pr_number}/{timepoint}/{lot}/preview-imc")
def get_preview_imc(pr_number: str, timepoint: str, lot: str, _user=Depends(get_current_user)):
    return list_preview_imc(pr_number, timepoint, lot)

@router.get("/product-request/{pr_number}/{timepoint}/{lot}/preview-bond")
def get_preview_bond(pr_number: str, timepoint: str, lot: str, _user=Depends(get_current_user)):
    return list_preview_bond(pr_number, timepoint, lot)

@router.get("/product-request/{pr_number}/{timepoint}/{lot}/preview-sem")
def get_preview_sem(pr_number: str, timepoint: str, lot: str, _user=Depends(get_current_user)):
    return list_preview_sem(pr_number, timepoint, lot)

def _resolve_image_path(path: str) -> pathlib.Path:
    """
    Translate the path from DB (which may be a Windows absolute path) to the
    actual filesystem path in this environment.

    IMAGE_WIN_ROOT  — prefix stored in DB  (default: D:\\Auto_detect\\Result)
    IMAGE_MOUNT_ROOT — where that folder is mounted here (default: same as WIN_ROOT)
    """
    win_root   = os.getenv("IMAGE_WIN_ROOT",   r"D:\Auto_detect\Result")
    mount_root = os.getenv("IMAGE_MOUNT_ROOT", win_root)

    # Normalise separators for comparison (handle both \ and /)
    norm_path = path.replace("\\", "/")
    norm_win  = win_root.replace("\\", "/")

    if norm_path.lower().startswith(norm_win.lower()):
        relative = norm_path[len(norm_win):].lstrip("/")
        path = str(pathlib.PurePosixPath(mount_root) / relative)

    return pathlib.Path(path)


@router.get("/image")
def get_image(path: str, _user=Depends(get_current_user)):
    """Serve an image from the Auto_detect Result folder."""
    mount_root = os.getenv("IMAGE_MOUNT_ROOT",
                           os.getenv("IMAGE_WIN_ROOT", r"D:\Auto_detect\Result"))
    _image_root = pathlib.Path(mount_root).resolve()
    requested   = _resolve_image_path(path).resolve()

    if not requested.is_relative_to(_image_root):
        raise HTTPException(status_code=403, detail="Access denied")
    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    ext = requested.suffix.lower()
    media_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
    return FileResponse(path=str(requested), media_type=media_type)


@router.post("/trigger-pipeline")
@limiter.limit("3/minute")
def trigger_pipeline(request: Request, _user=Depends(get_current_user)):
    """Trigger the auto-detect pipeline (System 1) to scan and process immediately."""
    # 1. Try via HTTP API first
    urls = [
        os.getenv("PIPELINE_TRIGGER_URL"),
        "http://localhost:9091/trigger",
        "http://host.docker.internal:9091/trigger",
    ]
    urls = list(dict.fromkeys([u for u in urls if u]))
    
    triggered_via_http = False
    http_error_msg = ""
    for url in urls:
        try:
            req = urllib.request.Request(url, data=b'')
            with urllib.request.urlopen(req, timeout=3.0) as response:
                if response.status == 200:
                    triggered_via_http = True
                    from logger import get_logger as _gl
                    _gl("product_request").info(f"Pipeline successfully triggered via HTTP URL: {url}")
                    break
        except Exception as e:
            http_error_msg = str(e)
            
    if triggered_via_http:
        return {"status": "success", "message": "Pipeline triggered successfully via HTTP API"}

    # 2. Try via docker CLI commands as fallbacks
    from logger import get_logger as _gl
    _log = _gl("product_request")
    _log.warning(f"Failed to trigger pipeline via HTTP URLs (last error: {http_error_msg}). Trying local Docker CLI fallback...")
    
    try:
        # Try docker restart first
        res = subprocess.run(["docker", "restart", "auto_detect-pipeline-1"], capture_output=True, text=True, timeout=10.0)
        if res.returncode == 0:
            _log.info("Pipeline container auto_detect-pipeline-1 restarted successfully")
            return {"status": "success", "message": "Pipeline triggered successfully via docker restart"}
        else:
            # Try docker-compose restart as second fallback
            res2 = subprocess.run(["docker-compose", "-f", r"D:\Auto_detect\docker-compose.yml", "restart", "pipeline"], capture_output=True, text=True, timeout=15.0)
            if res2.returncode == 0:
                _log.info("Pipeline restarted successfully via docker-compose restart")
                return {"status": "success", "message": "Pipeline triggered successfully via docker-compose restart"}
            else:
                raise Exception(f"docker restart failed: {res.stderr}; docker-compose restart failed: {res2.stderr}")
    except Exception as e:
        _log.error(f"Failed to trigger pipeline via Docker CLI fallback: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger pipeline. Error: {str(e)}"
        )


@router.get("/pipeline-status")
def pipeline_status(_user=Depends(get_current_user)):
    """Proxy the auto-detect watcher's run state (busy / cycle_count) so the UI
    overlay can wait until a triggered cycle actually finishes."""
    urls = [
        os.getenv("PIPELINE_STATUS_URL"),
        "http://localhost:9091/status",
        "http://host.docker.internal:9091/status",
    ]
    urls = list(dict.fromkeys([u for u in urls if u]))
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=3.0) as response:
                if response.status == 200:
                    import json as _json
                    return _json.loads(response.read().decode())
        except Exception:
            continue
    raise HTTPException(status_code=503, detail="Pipeline status unavailable")

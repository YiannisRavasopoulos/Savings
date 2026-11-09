"""Import expenses from a CSV file: upload -> preview (nothing saved) -> import."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from . import audit, db, importer, recurring
from .web import get_conn, redirect, render, user_id

router = APIRouter(prefix="/import")


def _options(form) -> dict:
    try:
        default = int(form.get("default_category_id") or 0) or None
    except ValueError:
        default = None
    return {"default_category_id": default, "create_missing": form.get("create_missing") == "1",
            "include_duplicates": form.get("include_duplicates") == "1"}


def _page(request, conn, status_code=200, **ctx):
    uid = user_id(request)
    ctx.setdefault("options", {"default_category_id": None, "create_missing": False, "include_duplicates": False})
    return render(request, "import.html", status_code, categories=db.active_categories(conn, uid),
                  max_rows=importer.MAX_ROWS, done=request.query_params.get("done"),
                  n=request.query_params.get("n", ""), **ctx)


@router.get("")
def page(request: Request, conn=Depends(get_conn)):
    return _page(request, conn)


@router.post("/preview")
async def preview(request: Request, conn=Depends(get_conn)):
    """From an uploaded file, or (after changing the options) from the text already uploaded."""
    form = await request.form()
    opts = _options(form)
    upload = form.get("file")
    try:
        if upload is not None and hasattr(upload, "read") and getattr(upload, "filename", ""):
            text = importer.decode(await upload.read(importer.MAX_BYTES + 1))
            filename = upload.filename
        else:
            text, filename = form.get("csv_text") or "", form.get("filename") or ""
            if not text.strip():
                raise importer.ImportError_("Choose a CSV file first.")
            if len(text.encode()) > importer.MAX_BYTES:
                raise importer.ImportError_("The file is too large.")
        result = importer.parse(conn, user_id(request), text, default_category_id=opts["default_category_id"],
                                create_missing=opts["create_missing"])
    except importer.ImportError_ as e:
        return _page(request, conn, 422, error=str(e), options=opts)
    return _page(request, conn, result=result, csv_text=text, filename=filename, options=opts)


@router.post("/confirm")
async def confirm(request: Request, conn=Depends(get_conn)):
    form = await request.form()
    opts = _options(form)
    uid = user_id(request)
    text = form.get("csv_text") or ""
    try:
        if len(text.encode()) > importer.MAX_BYTES:
            raise importer.ImportError_("The file is too large.")
        result = importer.parse(conn, uid, text, default_category_id=opts["default_category_id"],
                                create_missing=opts["create_missing"])
    except importer.ImportError_ as e:
        return _page(request, conn, 422, error=str(e), options=opts)
    wanted = {"ok", "duplicate"} if opts["include_duplicates"] else {"ok"}
    rows = [r for r in result["rows"] if r["status"] in wanted]
    if not rows:
        return _page(request, conn, 422, error="Nothing to import: no row is ready.", result=result,
                     csv_text=text, filename=form.get("filename") or "", options=opts)
    with conn:
        new_ids = {}
        for name in result["new_categories"]:
            if not any(r["new_category"] and r["category"] == name for r in rows):
                continue
            cur = conn.execute(
                "INSERT INTO categories (user_id, name, sort_order) "
                "VALUES (?, ?, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories WHERE user_id = ?))",
                (uid, name, uid))
            new_ids[name] = cur.lastrowid
            audit.log(conn, uid, "category.added", f"Added the category “{name}” (CSV import)", category_id=cur.lastrowid)
        for r in rows:
            cid = new_ids[r["category"]] if r["new_category"] else r["category_id"]
            recurring.insert_expense(conn, uid, {"date": r["date"], "description": r["description"],
                                                 "category_id": cid, "amount_cents": r["amount_cents"],
                                                 "notes": r["notes"], "one_off": r["one_off"]})
        first, last = min(r["date"] for r in rows), max(r["date"] for r in rows)
        audit.log(conn, uid, "expense.imported",
                  f"Imported {len(rows)} expense{'' if len(rows) == 1 else 's'} from a CSV file "
                  f"(dated {first} to {last})")
    return redirect(f"/import?done=1&n={len(rows)}")

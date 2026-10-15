"""
Biometric templates a reader has sent to the server (table employeesbio), and counts for the Users panel.

One FACE row per person, and one FINGER row per finger (FingerIndex 0-9). Rows saved before FingerIndex
existed have FingerIndex NULL; they count as one finger and are adopted by the first finger that arrives.
Camera faces (employeefaceembeddings, used by Aveon's own matching) are a separate thing and are not counted.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import EmployeeBio, EmployeePhoto

CAMERA_PHOTO_SOURCES = ("FaceEnroll", "AutoLearn", "CameraCapture")  # taken by Aveon's camera, not held by a reader
_CHUNK = 1000  # SQL Server allows about 2100 parameters per statement


def parse_finger_index(value: Optional[str]) -> int:
    try:
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def upsert_template(
    db: Session,
    employee_code: str,
    bio_name: str,
    template: str,
    description: str,
    finger_index: Optional[int] = None,
    major_ver: Optional[str] = None,
    minor_ver: Optional[str] = None,
) -> None:
    """Save or refresh one template. Fingers are keyed by finger number when it is known; otherwise
    (faces, or callers that do not know the number) the newest row of that kind is updated, as before."""
    base = db.query(EmployeeBio).filter(EmployeeBio.EmployeeCode == employee_code, EmployeeBio.BioName == bio_name)
    newest = EmployeeBio.EmployeeBioId.desc()
    keyed = bio_name == "FINGER" and finger_index is not None
    if keyed:
        row = (base.filter(EmployeeBio.FingerIndex == finger_index).order_by(newest).first()
               or base.filter(EmployeeBio.FingerIndex.is_(None)).order_by(newest).first())
    else:
        row = base.order_by(newest).first()
    if row is None:
        row = EmployeeBio(EmployeeCode=employee_code, BioName=bio_name)
        db.add(row)
    row.Bio = template
    row.BioDescription = description[:50]
    if keyed:
        row.FingerIndex = finger_index
    if major_ver is not None:
        row.MajorVer = major_ver
    if minor_ver is not None:
        row.MinorVer = minor_ver


FACE_PHOTO_NAME = "BIOPHOTO"  # the photo an AI-face reader enrolled the person from (OPERLOG BIOPHOTO)


def template_counts(db: Session, codes: Iterable[str]) -> tuple[dict[str, dict[str, int]], set[str], set[str]]:
    """({code: {"FACE": n, "FINGER": n}}, codes with a reader-sourced photo, codes with a face photo
    (BIOPHOTO: what an AI-face reader can build a face template from)) for the given people."""
    codes = list(dict.fromkeys(c for c in codes if c))
    counts: dict[str, dict[str, int]] = {}
    photos: set[str] = set()
    face_photos: set[str] = set()
    for i in range(0, len(codes), _CHUNK):
        part = codes[i:i + _CHUNK]
        for code, name, n in (
            db.query(EmployeeBio.EmployeeCode, EmployeeBio.BioName, func.count(EmployeeBio.EmployeeBioId))
            .filter(EmployeeBio.EmployeeCode.in_(part))
            .group_by(EmployeeBio.EmployeeCode, EmployeeBio.BioName)
            .all()
        ):
            counts.setdefault(code, {})[(name or "").upper()] = int(n)
        photos.update(
            c for (c,) in db.query(EmployeePhoto.EmployeeCode)
            .filter(EmployeePhoto.EmployeeCode.in_(part))
            .filter((EmployeePhoto.Source.is_(None)) | (~EmployeePhoto.Source.in_(CAMERA_PHOTO_SOURCES)))
            .distinct().all()
        )
        face_photos.update(
            c for (c,) in db.query(EmployeePhoto.EmployeeCode)
            .filter(EmployeePhoto.EmployeeCode.in_(part), EmployeePhoto.PhotoName == FACE_PHOTO_NAME)
            .distinct().all()
        )
    return counts, photos, face_photos

#!/usr/bin/env python3
"""Select confirmation images by identity gate."""

import argparse
import itertools
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_record import append_event, face_similarity_summary, refresh_markdown


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve(path, root):
    value = Path(path).expanduser()
    return value if value.is_absolute() else root / value


def successful_slots(manifest, root):
    slots = []
    for item in manifest.get("slots", []):
        if item.get("status") != "success" or not item.get("image_path"):
            continue
        path = resolve(item["image_path"], root)
        slots.append({**item, "resolved_image_path": str(path)})
    return slots


def bbox_area(face):
    bbox = getattr(face, "bbox", None)
    if bbox is None or len(bbox) < 4:
        return 0.0
    return max(0.0, float(bbox[2] - bbox[0])) * max(0.0, float(bbox[3] - bbox[1]))


def cosine_percent(left, right):
    import numpy as np

    value = float(np.dot(left, right))
    return round(max(0.0, min(100.0, value * 100.0)), 2)


def load_insightface_app(model_name, det_size):
    try:
        from insightface.app import FaceAnalysis
    except Exception as exc:
        raise RuntimeError("InsightFace 未安装；请先安装 TOOLS/requirements.txt 中的依赖") from exc

    providers = ["CPUExecutionProvider"]
    app = FaceAnalysis(name=model_name, providers=providers)
    app.prepare(ctx_id=-1, det_size=det_size)
    return app


def read_image(path):
    import cv2

    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f"无法读取图片：{path}")
    return image


FACE_LANDMARKER_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"


def ensure_face_landmarker_model(path):
    path = Path(path)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(FACE_LANDMARKER_URL, path)
    return path


def detect_face_meshes(image, model_path):
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
    except Exception:
        return {
            "available": False,
            "faces": [],
            "reason": "mediapipe unavailable; visibility defaults to 1.0",
        }

    try:
        model_path = ensure_face_landmarker_model(model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=5,
        )
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        with vision.FaceLandmarker.create_from_options(options) as landmarker:
            result = landmarker.detect(mp_image)
    except Exception as exc:
        return {
            "available": False,
            "faces": [],
            "reason": f"mediapipe face landmarker failed; visibility defaults to 1.0: {exc}",
        }

    return {
        "available": True,
        "faces": result.face_landmarks or [],
        "model_path": str(model_path),
    }


def face_visibility_from_meshes(mesh_result, image_shape, face_bbox):
    if not mesh_result.get("available"):
        return {
            "available": False,
            "face_visible_ratio": 1.0,
            "reason": mesh_result.get("reason", "mediapipe unavailable; visibility defaults to 1.0"),
        }

    height, width = image_shape[:2]
    x1, y1, x2, y2 = [float(value) for value in face_bbox]
    all_faces = mesh_result.get("faces") or []
    if not all_faces:
        return {
            "available": True,
            "face_visible_ratio": 0.0,
            "landmarks_total": 0,
            "landmarks_inside_bbox": 0,
            "reason": "no mediapipe face mesh detected",
        }

    best_inside = 0
    best_total = 0
    for face in all_faces:
        total = len(face)
        inside = 0
        for point in face:
            px = point.x * width
            py = point.y * height
            if x1 <= px <= x2 and y1 <= py <= y2:
                inside += 1
        if inside > best_inside:
            best_inside = inside
            best_total = total

    ratio = round(best_inside / best_total, 4) if best_total else 0.0
    return {
        "available": True,
        "face_visible_ratio": ratio,
        "landmarks_total": best_total,
        "landmarks_inside_bbox": best_inside,
        "model_path": mesh_result.get("model_path"),
    }


def expanded_bbox(face_bbox, image_shape, pad_ratio=0.75):
    bbox = bounded_bbox(face_bbox, image_shape)
    if bbox is None:
        return None
    height, width = image_shape[:2]
    x1, y1, x2, y2 = bbox
    pad_x = int(round((x2 - x1) * pad_ratio))
    pad_y = int(round((y2 - y1) * pad_ratio))
    return (
        max(0, x1 - pad_x),
        max(0, y1 - pad_y),
        min(width, x2 + pad_x),
        min(height, y2 + pad_y),
    )


def visibility_with_crop_retry(image, mesh_result, face_bbox, face_mesh_model):
    visibility = face_visibility_from_meshes(mesh_result, image.shape, face_bbox)
    visibility.update({
        "fallback_used": False,
        "mesh_detection_source": "full_image",
    })
    if (
        not visibility.get("available")
        or visibility.get("landmarks_total", 0) != 0
        or visibility.get("reason") != "no mediapipe face mesh detected"
    ):
        return visibility

    crop_box = expanded_bbox(face_bbox, image.shape)
    if crop_box is None:
        return {
            **visibility,
            "fallback_used": True,
            "mesh_detection_source": "insightface_bbox_crop",
            "crop_box_original_image": None,
            "reason": "invalid InsightFace bbox; no mediapipe face mesh crop retry",
        }

    x1, y1, x2, y2 = crop_box
    crop = image[y1:y2, x1:x2]
    crop_bbox = [
        float(face_bbox[0]) - x1,
        float(face_bbox[1]) - y1,
        float(face_bbox[2]) - x1,
        float(face_bbox[3]) - y1,
    ]
    crop_mesh = detect_face_meshes(crop, face_mesh_model)
    crop_visibility = face_visibility_from_meshes(crop_mesh, crop.shape, crop_bbox)
    if crop_visibility.get("available") and crop_visibility.get("landmarks_total", 0) == 0:
        crop_visibility["reason"] = "no mediapipe face mesh detected after one bbox crop retry"
    crop_visibility.update({
        "fallback_used": True,
        "mesh_detection_source": "insightface_bbox_crop",
        "crop_box_original_image": [x1, y1, x2, y2],
        "crop_scale": 1.0,
    })
    return crop_visibility


def bounded_bbox(face_bbox, image_shape):
    height, width = image_shape[:2]
    if face_bbox is None or len(face_bbox) < 4:
        return None
    x1, y1, x2, y2 = [int(round(float(value))) for value in face_bbox[:4]]
    x1 = max(0, min(width, x1))
    x2 = max(0, min(width, x2))
    y1 = max(0, min(height, y1))
    y2 = max(0, min(height, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def region_skin_ratio(skin_mask, region):
    x1, y1, x2, y2 = region
    roi = skin_mask[y1:y2, x1:x2]
    if roi.size == 0:
        return None
    return round(float(roi.mean()), 4)


def skin_occlusion_metrics(image, face_bbox):
    try:
        import cv2
    except Exception:
        return {
            "available": False,
            "physical_visible_ratio": 1.0,
            "likely_physical_occlusion": False,
            "reason": "opencv unavailable; skin coverage defaults to 1.0",
        }

    bbox = bounded_bbox(face_bbox, image.shape)
    if bbox is None:
        return {
            "available": False,
            "physical_visible_ratio": 1.0,
            "likely_physical_occlusion": False,
            "reason": "invalid face bbox; skin coverage defaults to 1.0",
        }

    x1, y1, x2, y2 = bbox
    face = image[y1:y2, x1:x2]
    height, width = face.shape[:2]
    hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    ycrcb = cv2.cvtColor(face, cv2.COLOR_BGR2YCrCb)

    hsv_skin = (
        ((hsv[:, :, 0] <= 25) | (hsv[:, :, 0] >= 165))
        & (hsv[:, :, 1] >= 25)
        & (hsv[:, :, 1] <= 190)
        & (hsv[:, :, 2] >= 55)
    )
    ycc_skin = (
        (ycrcb[:, :, 1] >= 133)
        & (ycrcb[:, :, 1] <= 173)
        & (ycrcb[:, :, 2] >= 77)
        & (ycrcb[:, :, 2] <= 127)
    )
    skin = hsv_skin & ycc_skin
    regions = {
        "whole": (0, 0, width, height),
        "central": (int(width * 0.25), int(height * 0.18), int(width * 0.75), int(height * 0.82)),
        "lower_central": (int(width * 0.25), int(height * 0.45), int(width * 0.75), int(height * 0.90)),
        "mouth_chin": (int(width * 0.20), int(height * 0.55), int(width * 0.80), int(height * 0.95)),
    }
    ratios = {f"{name}_skin_ratio": region_skin_ratio(skin, region) for name, region in regions.items()}
    lower_ratio = ratios["lower_central_skin_ratio"] or 0.0
    mouth_ratio = ratios["mouth_chin_skin_ratio"] or 0.0
    whole_ratio = ratios["whole_skin_ratio"] or 0.0
    likely_occlusion = lower_ratio < 0.45 or mouth_ratio < 0.35
    skin_visible_ratio = min(whole_ratio, lower_ratio, mouth_ratio)
    return {
        "available": True,
        **ratios,
        "physical_visible_ratio": round(skin_visible_ratio, 4),
        "skin_visible_ratio": round(skin_visible_ratio, 4),
        "likely_physical_occlusion": likely_occlusion,
        "bbox": [x1, y1, x2, y2],
    }


def combine_visibility(mesh_visibility, occlusion_metrics):
    mesh_ratio = mesh_visibility.get("face_visible_ratio", 1.0)
    physical_ratio = occlusion_metrics.get("physical_visible_ratio", 1.0)
    effective_ratio = min(float(mesh_ratio), float(physical_ratio))
    reasons = ["mediapipe_face_mesh", "skin_coverage"]
    return {
        **mesh_visibility,
        "face_visible_ratio": round(max(0.0, min(1.0, effective_ratio)), 4),
        "mediapipe_face_visible_ratio": mesh_ratio,
        "physical_visible_ratio": physical_ratio,
        "skin_occlusion": occlusion_metrics,
        "visibility_policy": "+".join(reasons),
    }


def adjusted_threshold(base_threshold, face_visible_ratio, min_threshold):
    ratio = max(0.0, min(1.0, float(face_visible_ratio)))
    return round(max(float(min_threshold), float(base_threshold) * ratio), 2)


def extract_faces(app, path, face_mesh_model):
    image = read_image(path)
    height, width = image.shape[:2]
    image_area = max(1.0, float(width * height))
    mesh_result = detect_face_meshes(image, face_mesh_model)
    faces = app.get(image)
    result = []
    for index, face in enumerate(faces):
        embedding = getattr(face, "normed_embedding", None)
        if embedding is None:
            continue
        area = bbox_area(face)
        face_bbox = getattr(face, "bbox", [])
        mesh_visibility = visibility_with_crop_retry(image, mesh_result, face_bbox, face_mesh_model)
        occlusion_metrics = skin_occlusion_metrics(image, face_bbox)
        visibility = combine_visibility(mesh_visibility, occlusion_metrics)
        result.append({
            "index": index,
            "bbox": [float(value) for value in getattr(face, "bbox", [])],
            "det_score": float(getattr(face, "det_score", 0.0)),
            "area": area,
            "area_ratio": round(area / image_area, 6),
            "visibility": visibility,
            "image_width": width,
            "image_height": height,
            "embedding": embedding,
        })
    return sorted(result, key=lambda item: item["area"], reverse=True)


def role_embeddings(app, role_paths, face_mesh_model):
    roles = {}
    for role, path in role_paths.items():
        faces = extract_faces(app, path, face_mesh_model)
        if not faces:
            roles[role] = {"ok": False, "error": "role image has no detectable face", "path": str(path)}
            continue
        selected = faces[0]
        roles[role] = {
            "ok": True,
            "path": str(path),
            "face": {
                "bbox": selected["bbox"],
                "det_score": selected["det_score"],
                "area": selected["area"],
                "area_ratio": selected["area_ratio"],
                "visibility": selected.get("visibility"),
                "image_width": selected["image_width"],
                "image_height": selected["image_height"],
            },
            "embedding": selected["embedding"],
        }
    return roles


def best_role_assignment(role_data, candidate_faces, max_candidate_faces=None, min_threshold=0.0):
    role_names = list(role_data)
    if any(not role_data[role].get("ok") for role in role_names):
        return None, "role face unavailable"

    if max_candidate_faces:
        candidate_faces = candidate_faces[:max_candidate_faces]
    if len(candidate_faces) < len(role_names):
        return {
            "checks": {
                role: {
                    "ok": True,
                    "skipped": True,
                    "skip_reason": "candidate has no comparable InsightFace face; face is treated as out of frame",
                    "auto_pass": True,
                    "auto_pass_reason": "candidate has no comparable InsightFace face",
                    "similarity_percent": None,
                    "base_threshold_percent": role_data[role].get("threshold", 75.0),
                    "face_visible_ratio": 0.0,
                    "min_threshold_percent": min_threshold,
                    "adjusted_threshold_percent": 0.0,
                    "mediapipe_visibility": None,
                    "candidate_face_index": None,
                    "candidate_face_bbox": None,
                    "candidate_face_det_score": None,
                    "candidate_face_area_ratio": None,
                }
                for role in role_names
            },
            "face_similarity_min_percent": None,
            "adjusted_threshold_min_percent": 0.0,
            "face_similarity_margin_min_percent": 0.0,
            "face_gate_skipped": True,
            "face_gate_skip_reason": "candidate has no comparable InsightFace face; face is treated as out of frame",
        }, None

    best = None
    for face_perm in itertools.permutations(candidate_faces, len(role_names)):
        checks = {}
        similarities = []
        for role, face in zip(role_names, face_perm):
            percent = cosine_percent(role_data[role]["embedding"], face["embedding"])
            visibility = face.get("visibility") or {}
            visible_ratio = visibility.get("face_visible_ratio", 1.0)
            role_threshold = adjusted_threshold(role_data[role].get("threshold", 75.0), visible_ratio, min_threshold)
            checks[role] = {
                "ok": True,
                "similarity_percent": percent,
                "base_threshold_percent": role_data[role].get("threshold", 75.0),
                "face_visible_ratio": visible_ratio,
                "min_threshold_percent": min_threshold,
                "adjusted_threshold_percent": role_threshold,
                "mediapipe_visibility": visibility,
                "candidate_face_index": face["index"],
                "candidate_face_bbox": face["bbox"],
                "candidate_face_det_score": face["det_score"],
                "candidate_face_area_ratio": face.get("area_ratio"),
            }
            similarities.append({
                "similarity_percent": percent,
                "adjusted_threshold_percent": role_threshold,
                "pass_margin_percent": round(percent - role_threshold, 2),
            })
        min_similarity = min(item["similarity_percent"] for item in similarities)
        min_threshold = min(item["adjusted_threshold_percent"] for item in similarities)
        min_margin = min(item["pass_margin_percent"] for item in similarities)
        if best is None or min_margin > best["face_similarity_margin_min_percent"]:
            best = {
                "checks": checks,
                "face_similarity_min_percent": min_similarity,
                "adjusted_threshold_min_percent": min_threshold,
                "face_similarity_margin_min_percent": min_margin,
            }
    return best, None


def compare_candidates(app, role_paths, candidate_paths, threshold, max_candidate_faces=None, min_threshold=0.0, face_mesh_model=None):
    roles = role_embeddings(app, role_paths, face_mesh_model)
    for role in roles:
        roles[role]["threshold"] = threshold
    comparisons = {}
    for path in candidate_paths:
        try:
            faces = extract_faces(app, path, face_mesh_model)
            assignment, reason = best_role_assignment(
                roles,
                faces,
                max_candidate_faces=max_candidate_faces,
                min_threshold=min_threshold,
            )
            if assignment:
                comparisons[str(path)] = assignment
            else:
                comparisons[str(path)] = {
                    "checks": {
                        role: {
                            "ok": False,
                            "error": roles[role].get("error") if not roles[role].get("ok") else reason,
                        }
                        for role in roles
                    },
                    "face_similarity_min_percent": None,
                    "adjusted_threshold_min_percent": None,
                    "face_similarity_margin_min_percent": None,
                }
        except Exception as exc:
            comparisons[str(path)] = {
                "checks": {role: {"ok": False, "error": str(exc)} for role in roles},
                "face_similarity_min_percent": None,
                "adjusted_threshold_min_percent": None,
                "face_similarity_margin_min_percent": None,
            }
    return comparisons


def attach_similarity(slots, comparisons, threshold):
    enriched = []
    for slot in slots:
        path = slot["resolved_image_path"]
        result = comparisons.get(path, {"checks": {}, "face_similarity_min_percent": None})
        min_percent = result.get("face_similarity_min_percent")
        adjusted = result.get("adjusted_threshold_min_percent", threshold)
        margin = result.get("face_similarity_margin_min_percent")
        eligible = margin is not None and float(margin) >= 0
        face_gate_skipped = bool(result.get("face_gate_skipped"))
        reason = "pass" if eligible else f"face similarity below adjusted threshold {adjusted}% or unavailable"
        enriched.append({
            **slot,
            "face_similarity": result.get("checks", {}),
            "face_similarity_min_percent": min_percent,
            "base_threshold_percent": threshold,
            "adjusted_threshold_min_percent": adjusted,
            "face_similarity_margin_min_percent": margin,
            "face_gate_skipped": face_gate_skipped,
            "face_gate_skip_reason": result.get("face_gate_skip_reason"),
            "auto_select_eligible": eligible,
            "auto_select_reason": reason,
        })
    return enriched


def choose_best_slot(slots):
    eligible = [item for item in slots if item.get("auto_select_eligible")]
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda item: (
            -float(item.get("face_similarity_margin_min_percent") or -999),
            -float(item.get("face_similarity_min_percent") or 0),
            not bool(item.get("display")),
            str(item.get("slot") or ""),
        ),
    )[0]


def build_report(args):
    root = Path.cwd()
    manifest_path = resolve(args.manifest, root)
    manifest = read_json(manifest_path)
    slots = successful_slots(manifest, root)
    candidate_paths = [Path(item["resolved_image_path"]) for item in slots]
    role_paths = {"anna": resolve(args.anna_role, root)}

    max_candidate_faces = args.max_candidate_faces or len(role_paths)
    app = load_insightface_app(args.model, tuple(args.det_size))
    comparisons = compare_candidates(
        app,
        role_paths,
        candidate_paths,
        args.threshold,
        max_candidate_faces=max_candidate_faces,
        min_threshold=args.min_threshold,
        face_mesh_model=args.face_mesh_model,
    )
    enriched = attach_similarity(slots, comparisons, args.threshold)
    selected = choose_best_slot(enriched)
    errors = []
    if not selected:
        errors.append(f"没有确认图通过人脸一致性门禁（人脸基础 {args.threshold}%）")
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "decision": "pass" if selected else "fail",
        "method": "insightface",
        "model": args.model,
        "route": args.route,
        "threshold_percent": args.threshold,
        "min_threshold_percent": args.min_threshold,
        "threshold_policy": "face gate uses adjusted_threshold=threshold*effective_face_visible_ratio; if candidate has no comparable InsightFace face, face gate is skipped as out-of-frame",
        "face_mesh_model": str(args.face_mesh_model),
        "candidate_face_policy": f"largest {max_candidate_faces} face(s) by bounding-box area",
        "role_policy": "anna only",
        "manifest": str(manifest_path),
        "roles": {role: str(path) for role, path in role_paths.items()},
        "slots": enriched,
        "selected_slot": selected.get("slot") if selected else None,
        "selected_confirmation_image": selected.get("image_path") if selected else None,
        "errors": errors,
    }


def build_parser():
    parser = argparse.ArgumentParser(description="用 anna 人脸一致性筛选确认图。")
    parser.add_argument("--manifest", required=True, help="confirmation-manifest.json")
    parser.add_argument("--route", choices=["anna"], required=True)
    parser.add_argument("--threshold", type=float, default=75.0, help="无遮挡时的人脸相似度标准")
    parser.add_argument("--min-threshold", type=float, default=0.0, help="按脸部漏出比例调整后的最低相似度标准；默认 0 表示不设最低线")
    parser.add_argument("--model", default="buffalo_l", help="InsightFace model pack")
    parser.add_argument("--det-size", type=int, nargs=2, default=[640, 640], metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--face-mesh-model", default="TEMP/models/face_landmarker.task", help="MediaPipe Face Landmarker .task 模型路径，不存在时自动下载")
    parser.add_argument("--max-candidate-faces", type=int, default=None, help="候选图最多参与匹配的人脸数；默认 1")
    parser.add_argument("--anna-role", default="MATERIAL/fixed-role/anna.png")
    parser.add_argument("--out", required=True, help="输出 face-similarity-report.json")
    parser.add_argument("--record-jsonl", default=None, help="可选：追加写入 TEMP/RUN_ID/RUN_ID-run-record.jsonl")
    return parser


def main():
    args = build_parser().parse_args()

    try:
        report = build_report(args)
    except Exception as exc:
        print(json.dumps({"decision": "fail", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_json"] = str(out)
    if args.record_jsonl:
        summary = face_similarity_summary(report)
        append_event(
            args.record_jsonl,
            stage="confirmation",
            event="face_similarity",
            status=report["decision"],
            summary=f"人脸相似度门禁 {report['decision']}，选中 {report['selected_slot'] or '无'}",
            data=summary,
        )
        refresh_markdown(args.record_jsonl)
    print(json.dumps({
        "decision": report["decision"],
        "selected_slot": report["selected_slot"],
        "selected_confirmation_image": report["selected_confirmation_image"],
        "report": str(out),
        "errors": report["errors"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

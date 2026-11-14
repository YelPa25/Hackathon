"""Facial feature extraction module wrapping LibreFace.

Isolates LibreFace models and MediaPipe face landmark detection so models are
loaded once on initialization and reused across frame inference calls.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import cv2
import mediapipe as mp
import numpy as np
from PIL import Image
import torch

# Fix Pillow >= 10.0 deprecation of Image.ANTIALIAS used inside LibreFace
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from libreface.AU_Recognition.inference import ConfigObject, set_seed
from libreface.AU_Recognition.solver_inference_combine import (
    solver_inference_image_task_combine,
)
from libreface.Facial_Expression_Recognition.inference import facial_expr_idx_to_class
from libreface.Facial_Expression_Recognition.solver_inference_image import (
    solver_inference_image,
)
from libreface.detect_mediapipe_image import image_align


class LibreFaceExtractor:
    """Wrapper around LibreFace models with once-loaded neural network weights."""

    FACEMESH_LEFT_EYE = [
        (263, 249), (249, 390), (390, 373), (373, 374),
        (374, 380), (380, 381), (381, 382), (382, 362),
        (263, 466), (466, 388), (388, 387), (387, 386),
        (386, 385), (385, 384), (384, 398), (398, 362),
    ]

    FACEMESH_RIGHT_EYE = [
        (33, 7), (7, 163), (163, 144), (144, 145),
        (145, 153), (153, 154), (154, 155), (155, 133),
        (33, 246), (246, 161), (161, 160), (160, 159),
        (159, 158), (158, 157), (157, 173), (173, 133),
    ]

    FACEMESH_LIPS = [
        (61, 146), (146, 91), (91, 181), (181, 84), (84, 17),
        (17, 314), (314, 405), (405, 321), (321, 375),
        (375, 291), (61, 185), (185, 40), (40, 39), (39, 37),
        (37, 0), (0, 267), (267, 269), (269, 270), (270, 409), (409, 291),
        (78, 95), (95, 88), (88, 178), (178, 87), (87, 14),
        (14, 317), (317, 402), (402, 318), (318, 324),
        (324, 308), (78, 191), (191, 80), (80, 81), (81, 82),
        (82, 13), (13, 312), (312, 311), (311, 310),
        (310, 415), (415, 308),
    ]

    def __init__(
        self,
        device: str = "cpu",
        weights_download_dir: str = "./weights_libreface",
        include_expression: bool = False,
    ) -> None:
        """Initialize MediaPipe face mesh and LibreFace PyTorch solvers once."""
        self.device = device
        self.weights_download_dir = weights_download_dir
        self.include_expression = include_expression

        # Initialize MediaPipe Face Mesh
        mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        # Precompute unique landmark indices for alignment
        self.left_eye_indices = []
        for x, _ in self.FACEMESH_LEFT_EYE:
            if x not in self.left_eye_indices:
                self.left_eye_indices.append(x)
        self.right_eye_indices = []
        for x, _ in self.FACEMESH_RIGHT_EYE:
            if x not in self.right_eye_indices:
                self.right_eye_indices.append(x)
        self.lips_indices = []
        for x, _ in self.FACEMESH_LIPS:
            if x not in self.lips_indices:
                self.lips_indices.append(x)

        # Load LibreFace AU detection + recognition solver
        au_opts = ConfigObject({
            "seed": 0,
            "ckpt_path": os.path.join(
                self.weights_download_dir, "AU_Recognition", "weights", "combined_resnet.pt"
            ),
            "weights_download_id": "1CbnBr8OBt8Wb73sL1ENcrtrWAFWSSRv0",
            "image_inference": False,
            "au_recognition_data_root": "",
            "au_recognition_data": "DISFA",
            "au_detection_data_root": "",
            "au_detection_data": "BP4D",
            "fer_train_csv": "training_filtered.csv",
            "fer_test_csv": "validation_filtered.csv",
            "fer_data_root": "",
            "fer_data": "AffectNet",
            "fold": "all",
            "image_size": 256,
            "crop_size": 224,
            "au_recognition_num_labels": 12,
            "au_detection_num_labels": 12,
            "fer_num_labels": 8,
            "sigma": 10.0,
            "jitter": False,
            "copy_classifier": False,
            "model_name": "resnet",
            "dropout": 0.1,
            "ffhq_pretrain": "",
            "hidden_dim": 128,
            "fm_distillation": False,
            "num_epochs": 30,
            "interval": 500,
            "threshold": 0,
            "batch_size": 256,
            "learning_rate": 3e-5,
            "weight_decay": 1e-4,
            "clip": 1.0,
            "when": 10,
            "patience": 5,
            "device": self.device,
        })
        set_seed(au_opts.seed)
        self.au_solver = solver_inference_image_task_combine(au_opts).to(self.device)
        self.au_solver.eval()

        self.expression_solver = None
        if self.include_expression:
            expr_opts = ConfigObject({
                "seed": 0,
                "train_csv": "training_filtered.csv",
                "test_csv": "validation_filtered.csv",
                "data_root": "",
                "ckpt_path": os.path.join(
                    self.weights_download_dir,
                    "Facial_Expression_Recognition",
                    "weights",
                    "repvgg.pt",
                ),
                "weights_download_id": "1yPBUjPhkwcIkRLt47-JJRLRD7rCwPIVU",
                "data": "AffectNet",
                "image_size": 224,
                "num_labels": 8,
                "dropout": 0.1,
                "hidden_dim": 128,
                "sigma": 10.0,
                "student_model_name": "repvgg",
                "student_model_choices": ["repvgg"],
                "alpha": 1.0,
                "T": 1.0,
                "fm_distillation": True,
                "grad": True,
                "interval": 500,
                "threshold": 0.0,
                "loss": "unweighted",
                "num_epochs": 50,
                "batch_size": 256,
                "learning_rate": "3e-5",
                "weight_decay": "1e-4",
                "clip": 1.0,
                "when": 10,
                "patience": 10,
                "device": self.device,
            })
            set_seed(expr_opts.seed)
            self.expression_solver = solver_inference_image(expr_opts).to(self.device)
            self.expression_solver.eval()

    def _estimate_pose_and_landmarks(
        self, frame_bgr: np.ndarray, results: Any
    ) -> Tuple[Optional[Dict[str, float]], Optional[np.ndarray]]:
        """Calculate head pose angles (pitch, yaw, roll) and alignment landmarks."""
        if not results.multi_face_landmarks:
            return None, None

        img_h, img_w, _ = frame_bgr.shape
        face_landmarks = results.multi_face_landmarks[0]

        face_2d = []
        face_3d = []
        for idx, lm in enumerate(face_landmarks.landmark):
            if idx in (33, 263, 1, 61, 291, 199):
                x, y = int(lm.x * img_w), int(lm.y * img_h)
                face_2d.append([x, y])
                face_3d.append([x, y, lm.z])

        face_2d = np.array(face_2d, dtype=np.float64)
        face_3d = np.array(face_3d, dtype=np.float64)

        focal_length = 1.0 * img_w
        cam_matrix = np.array(
            [[focal_length, 0, img_h / 2.0], [0, focal_length, img_w / 2.0], [0, 0, 1.0]]
        )
        dist_matrix = np.zeros((4, 1), dtype=np.float64)

        success, rot_vec, _ = cv2.solvePnP(face_3d, face_2d, cam_matrix, dist_matrix)
        if not success:
            return None, None

        rmat, _ = cv2.Rodrigues(rot_vec)
        angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)

        head_pose = {
            "pitch": float(angles[0] * 360.0),
            "yaw": float(angles[1] * 360.0),
            "roll": float(angles[2] * 360.0),
        }

        lm_left_eye_x = [face_landmarks.landmark[i].x for i in self.left_eye_indices]
        lm_left_eye_y = [face_landmarks.landmark[i].y for i in self.left_eye_indices]
        lm_right_eye_x = [face_landmarks.landmark[i].x for i in self.right_eye_indices]
        lm_right_eye_y = [face_landmarks.landmark[i].y for i in self.right_eye_indices]
        lm_lips_x = [face_landmarks.landmark[i].x for i in self.lips_indices]
        lm_lips_y = [face_landmarks.landmark[i].y for i in self.lips_indices]

        lm_x = lm_left_eye_x + lm_right_eye_x + lm_lips_x
        lm_y = lm_left_eye_y + lm_right_eye_y + lm_lips_y
        landmarks = np.array([lm_x, lm_y]).T

        return head_pose, landmarks

    def extract_frame(self, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """Extract facial features from a single BGR frame.

        Returns a dictionary containing:
            face_detected (bool): whether a face was detected
            mean_brightness (float): 0-255 average grayscale brightness
            au_intensities (dict): mapping from 'au_X_intensity' to float [0, 5]
            detected_aus (dict): mapping from 'au_X' to int (0 or 1)
            head_pose (dict or None): {'pitch': float, 'yaw': float, 'roll': float}
            expression (str or None): detected discrete expression label
        """
        if frame_bgr is None or frame_bgr.size == 0:
            return {
                "face_detected": False,
                "mean_brightness": 0.0,
                "au_intensities": {},
                "detected_aus": {},
                "head_pose": None,
                "expression": None,
            }

        # Compute mean brightness
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))

        # MediaPipe face detection & landmark extraction
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(frame_rgb)

        head_pose, landmarks = self._estimate_pose_and_landmarks(frame_bgr, results)
        if head_pose is None or landmarks is None:
            return {
                "face_detected": False,
                "mean_brightness": mean_brightness,
                "au_intensities": {},
                "detected_aus": {},
                "head_pose": None,
                "expression": None,
            }

        # Align face in-memory without disk I/O
        pil_img = Image.fromarray(frame_rgb)
        aligned_pil = image_align(pil_img, landmarks)

        # AU inference
        transformed_img = self.au_solver.image_transform(aligned_pil)
        with torch.no_grad():
            raw_rec = self.au_solver.image_inference_au_recognition(transformed_img)
            rec_vals = raw_rec.squeeze().tolist()
            if not isinstance(rec_vals, list):
                rec_vals = [rec_vals]

            raw_det = self.au_solver.image_inference_au_detection(transformed_img)
            det_vals = raw_det.squeeze().tolist()
            if not isinstance(det_vals, list):
                det_vals = [det_vals]

        au_intensities = {
            f"au_{au}_intensity": float(val)
            for au, val in zip(self.au_solver.au_recognition_aus, rec_vals)
        }
        detected_aus = {
            f"au_{au}": int(val)
            for au, val in zip(self.au_solver.au_detection_aus, det_vals)
        }

        expression = None
        if self.expression_solver is not None:
            with torch.no_grad():
                expr_img = aligned_pil.resize(
                    (self.expression_solver.img_size[0], self.expression_solver.img_size[1])
                )
                expr_tensor = self.expression_solver.convert(expr_img)
                expr_tensor = self.expression_solver.transform(expr_tensor)
                expr_pred = self.expression_solver.image_inference(expr_tensor)
                expression = facial_expr_idx_to_class(expr_pred.squeeze().tolist())

        return {
            "face_detected": True,
            "mean_brightness": mean_brightness,
            "au_intensities": au_intensities,
            "detected_aus": detected_aus,
            "head_pose": head_pose,
            "expression": expression,
        }

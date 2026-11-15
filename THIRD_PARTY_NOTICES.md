# Third-party notices

The repository's [Apache-2.0 license](LICENSE) covers original ASTRA contributions, including the synthetic data and generator. The main source tree does not vendor package installations, model weights, or raw device captures. Install upstream packages from the pinned manifests and retain each package's copyright, license and NOTICE files when redistributing its code or binaries.

## Required runtimes and dependencies

| Component and verified version | License and upstream source | Role |
| --- | --- | --- |
| CPython 3.12.10 and its SQLite library | [PSF-2.0](https://docs.python.org/3.12/license.html), [SQLite public-domain dedication](https://sqlite.org/copyright.html) | Core backend and storage. |
| uv 0.12.10 | [MIT or Apache-2.0](https://github.com/astral-sh/uv) | Recreates the locked Python environment. |
| Node.js 26.13.1 and npm 11.20.0 | [Node.js MIT and bundled notices](https://github.com/nodejs/node/blob/main/LICENSE), [npm CLI Artistic-2.0](https://github.com/npm/cli/blob/latest/LICENSE) | Frontend tooling and lockfile installation. |
| FastAPI 0.162.7, Pydantic 2.14.3, Uvicorn 0.54.0 | [FastAPI MIT](https://github.com/fastapi/fastapi), [Pydantic MIT](https://github.com/pydantic/pydantic), [Uvicorn BSD-3-Clause](https://github.com/encode/uvicorn) | API, data validation, and ASGI server. |
| HTTPX2 2.16.0 and pytest 9.2.0 | [HTTPX2 BSD-3-Clause](https://pypi.org/project/httpx2/2.16.0/), [pytest MIT](https://github.com/pytest-dev/pytest) | Backend verification tools. |
| React and React DOM 19.3.1, React Router 7.13.0, Recharts 3.10.1 | [React MIT](https://github.com/facebook/react), [React Router MIT](https://github.com/remix-run/react-router), [Recharts MIT](https://github.com/recharts/recharts) | User interface, navigation, and charts. |
| Tailwind CSS 4.3.5, Vite 8.3.8, TypeScript 5.9.3 | [Tailwind MIT](https://github.com/tailwindlabs/tailwindcss), [Vite MIT](https://github.com/vitejs/vite), [TypeScript Apache-2.0](https://github.com/microsoft/TypeScript) | Styling, build tooling, and type checking. |
| ESLint and @eslint/js 10.15.0/10.0.1, typescript-eslint 8.72.2, eslint-plugin-react-hooks 7.1.1 | [ESLint MIT](https://github.com/eslint/eslint), [typescript-eslint MIT](https://github.com/typescript-eslint/typescript-eslint), [React MIT](https://github.com/facebook/react) | Frontend development checks. |
| lucide-react 0.577.0 | [ISC, with MIT notice for inherited Feather icons](https://github.com/lucide-icons/lucide/blob/main/LICENSE) | Interface icons. Keep upstream icon notices with redistributed bundles. |

[backend/uv.lock](backend/uv.lock) and [frontend/package-lock.json](frontend/package-lock.json) record package sources, versions and hashes. The npm lock also records declared licenses. The wheels and npm archives provide their own license notices.

## Optional local runtimes and models

| Component or model | Source and license | Availability and redistribution |
| --- | --- | --- |
| Ollama 0.40.16 | [Ollama, MIT](https://github.com/ollama/ollama/blob/main/LICENSE) | External runtime. Install using the [Windows guide](https://ollama.com/download/windows). |
| qwen3:4b-instruct-2507-q4_K_M | [Ollama tag](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M), [Qwen3-4B-Instruct-2507, Apache-2.0](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | Optional recreational chat weights. Pull from Ollama, about 2.5 GB. |
| LibreFace 0.2.0 and combined AU checkpoint | [Package](https://pypi.org/project/libreface/0.2.0/), [USC Research Licence](https://github.com/ihp-lab/LibreFace/blob/main/LICENSE.rst), [upstream publication](https://openaccess.thecvf.com/content/WACV2024/html/Chang_LibreFace_An_Open-Source_Toolkit_for_Deep_Facial_Expression_Analysis_WACV_2024_paper.html) | Optional research use. Permission is limited by the upstream license. Package and checkpoint are excluded from ASTRA. Obtain the checkpoint through LibreFace and verify the pinned hash before use. |
| openSMILE 2.6.0 and eGeMAPS | [Package](https://pypi.org/project/opensmile/2.6.0/), [audEERING research terms](https://github.com/audeering/opensmile/blob/master/LICENSE) | Optional live speech extraction. The shipped native engine has research terms with commercial restrictions. The Python wrapper’s project metadata alone does not establish rights to the native engine. |
| PyTorch 2.0.1+cpu, TorchVision 0.15.2+cpu, TorchAudio 2.0.2+cpu | [PyTorch BSD-3-Clause](https://github.com/pytorch/pytorch/blob/v2.0.1/LICENSE), [TorchVision BSD-3-Clause](https://github.com/pytorch/vision/blob/v0.15.2/LICENSE), [TorchAudio BSD-2-Clause](https://github.com/pytorch/audio/blob/v2.0.2/LICENSE) | Optional Windows CPU runtime. Retain bundled upstream component notices. The separate [ResNet-18 checkpoint](https://download.pytorch.org/models/resnet18-f37072fd.pth) is obtained from TorchVision’s host. Review the model and training data terms before redistribution. |
| MediaPipe 0.10.5, OpenCV contrib wheel 4.11.0.86, Transformers 4.44.2 | [MediaPipe Apache-2.0](https://github.com/google-ai-edge/mediapipe), [OpenCV wheel licensing](https://github.com/opencv/opencv-python#licensing), [Transformers Apache-2.0](https://github.com/huggingface/transformers) | Optional video and model dependencies. Review bundled wheel notices, including licenses for libraries used by OpenCV. |
| Silero VAD at 6478567 | [MIT license at source revision](https://github.com/snakers4/silero-vad/blob/6478567951ae5c9979ad7b234185b5515f4be7a1/LICENSE) | Optional voice segmentation. The [capture guide](docs/LIVE_RESEARCH_CAPTURE.md) pins the JIT and helper files. |
| Meta wav2vec2-xls-r-300m at 1a640f3 | [Pinned model card and artifacts, Apache-2.0](https://huggingface.co/facebook/wav2vec2-xls-r-300m/tree/1a640f32ac3e39899438a2931f9924c02f080a54) | Optional voice embedding. Obtain upstream, about 1.27 GB. |
| Parselmouth 0.4.7, sounddevice 0.5.6, SoundFile 0.13.1, Pillow 11.3.0 | [Parselmouth GPL-3.0](https://github.com/YannickJadoul/Parselmouth), [sounddevice MIT](https://github.com/spatialaudio/python-sounddevice), [SoundFile BSD-3-Clause](https://github.com/bastibe/python-soundfile), [Pillow MIT-CMU](https://pillow.readthedocs.io/en/stable/about.html#license) | Optional audio and image support. Preserve notices for shipped native libraries, including libsndfile where applicable. |
| NumPy 1.26.4, SciPy 1.15.3, scikit-learn 1.3.2, PyYAML 6.0.2 | [NumPy BSD-3-Clause](https://github.com/numpy/numpy), [SciPy BSD-3-Clause](https://github.com/scipy/scipy), [scikit-learn BSD-3-Clause](https://github.com/scikit-learn/scikit-learn), [PyYAML MIT](https://github.com/yaml/pyyaml) | Optional detector tests and prototypes. The dataset generator uses NumPy. |

See [the Windows research manifest](face_speech/live/requirements-windows.txt) for the supporting packages. The upstream research requirements are preserved as historical handoff material. Core, synthetic research playback, and Companion do not need live capture packages. For competition use, confirm the scope of any optional restricted components against the [participant terms](https://www.spaceappschallenge.org/legal/).

## Bundled art, fonts, and scientific sources

- **Earth backdrop and screenshots that depict it.** NASA/NOAA/GSFC/Suomi NPP/VIIRS/Norman Kuring, [Blue Marble, 2012](https://www.nasa.gov/image-article/blue-marble-2012/). ASTRA bundles a resized JPEG and adds shading through CSS. Use is subject to [NASA media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/) and implies no endorsement. The screenshots depict the real console with synthetic mission data.
- **Typography.** The console uses system fonts. Font binaries are not bundled.
- **Scientific references.** The CSV [source catalog](ASTRA_90day_dataset_v1/scientific_sources.csv) and [methodology](docs/HEALTH_INTELLIGENCE_METHODOLOGY.md) identify NASA, CDC and NIST sources. ASTRA includes citations and original synthetic observations. No external individual-level research dataset or original publication is redistributed.

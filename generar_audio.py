#!/usr/bin/env python3
"""Genera la narración Microsoft Alex (es-PE) y tiempos para GitHub Pages.

Requiere internet, edge-tts, pydub y ffmpeg. Para usar con GitHub Actions.
La voz se consulta a Microsoft mediante edge-tts; su disponibilidad puede variar.
"""
from __future__ import annotations

import asyncio
import json
import re
import tempfile
from pathlib import Path

import edge_tts
from pydub import AudioSegment

ROOT = Path(__file__).resolve().parent
VOICE = "es-PE-AlexNeural"
OUTPUT_DIR = ROOT / "audio"
OUTPUT_MP3 = OUTPUT_DIR / "meditacion_alex_es_PE.mp3"
OUTPUT_TIMELINE = OUTPUT_DIR / "timeline.json"


def load_sections() -> list[dict]:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    match = re.search(
        r'<script\s+type="application/json"\s+id="meditation-data">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    if not match:
        raise RuntimeError("No aparece el guion de la meditación en index.html")
    sections = json.loads(match.group(1))
    if not sections or not all(isinstance(x.get("text"), str) and x["text"].strip() and isinstance(x.get("pause"), (int, float)) and x["pause"] >= 0 for x in sections):
        raise ValueError("Los fragmentos del guion tienen un formato inválido")
    return sections


async def create_audio() -> None:
    sections = load_sections()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    combined = AudioSegment.silent(duration=300, frame_rate=24_000).set_channels(1)
    timings = []

    with tempfile.TemporaryDirectory(prefix="meditacion_alex_") as tempdir:
        for i, segment in enumerate(sections):
            print(f"Generando {i + 1}/{len(sections)} con {VOICE}...", flush=True)
            temp_mp3 = Path(tempdir) / f"parte_{i:02d}.mp3"
            # Se sintetiza cada fragmento para poder mantener las pausas guiadas.
            communication = edge_tts.Communicate(
                segment["text"], voice=VOICE, rate="-10%"
            )
            await communication.save(str(temp_mp3))
            if not temp_mp3.exists() or temp_mp3.stat().st_size < 300:
                raise RuntimeError(f"El servicio no produjo audio para el fragmento {i + 1}")
            speech = AudioSegment.from_file(temp_mp3, format="mp3")
            speech = speech.set_frame_rate(24_000).set_channels(1)
            if len(speech) < 250:
                raise RuntimeError(f"Audio demasiado corto en el fragmento {i + 1}")

            start = len(combined) / 1000
            combined += speech
            end = len(combined) / 1000
            duration_pause = round(segment["pause"] * 1000)
            combined += AudioSegment.silent(duration=duration_pause, frame_rate=24_000)
            timings.append(
                {"start": round(start, 3), "end": round(end, 3), "after": round(len(combined) / 1000, 3)}
            )

    # Exportar a archivos temporales y reemplazar al finalizar, evitando una web rota.
    temp_output = OUTPUT_DIR / "meditacion_alex_es_PE.tmp.mp3"
    temp_timeline = OUTPUT_DIR / "timeline.tmp.json"
    try:
        combined.export(temp_output, format="mp3", bitrate="80k")
        if not temp_output.exists() or temp_output.stat().st_size < 20000:
            raise RuntimeError("No se pudo generar el MP3 completo")
        timeline_data = {
            "voice": VOICE,
            "locale": "es-PE",
            "name": "Microsoft Alex Online (Natural) - Spanish (Peru)",
            "duration": round(len(combined) / 1000, 3),
            "timeline": timings,
        }
        temp_timeline.write_text(json.dumps(timeline_data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_output.replace(OUTPUT_MP3)
        temp_timeline.replace(OUTPUT_TIMELINE)
        print(f"LISTO: {OUTPUT_MP3.name}, {OUTPUT_TIMELINE.name} ({len(combined)/1000:.1f} s)")
    finally:
        temp_output.unlink(missing_ok=True)
        temp_timeline.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(create_audio())

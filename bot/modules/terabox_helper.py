"""
terabox_helper.py
------------------
Modul tambahan untuk mengunduh file dari Terabox, dipakai sebagai plugin
di dalam repo anasty17/mirror-leech-telegram-bot (MLTB).

Cara kerja singkat:
1. Login ke akun Terabox kamu sendiri memakai cookie (ndus, csrfToken, browserid)
   yang diambil dari browser setelah kamu login manual.
2. Buka/"save" link share Terabox yang mau di-download ke akun kamu.
3. Ambil direct download link dari file tersebut.
4. Download file itu ke folder download lokal bot (folder yang sama
   dipakai MLTB untuk file direct-link biasa), lalu biarkan pipeline
   upload MLTB yang sudah ada menanganinya (ke Telegram / GDrive / rclone).

CATATAN PENTING:
- Ini BUKAN API resmi Terabox. Library aioterabox melakukan reverse-engineering
  terhadap web client Terabox, jadi bisa berhenti bekerja kapan saja kalau
  Terabox mengubah sistem mereka.
- Karena kamu pakai bot ini secara privat, pastikan login pakai akun Terabox
  milikmu sendiri dan jangan bagikan cookie session ke orang lain (itu setara
  akses penuh ke akunmu).
- Pertimbangkan Terms of Service Terabox sebelum menggunakan ini.
"""

import asyncio
import os
from pathlib import Path

import aiohttp
from aioterabox.api import TeraboxClient

# ── Konfigurasi: isi lewat environment variable, JANGAN hardcode di kode ──
TERABOX_NDUS = os.environ.get("TERABOX_NDUS", "")
TERABOX_CSRF_TOKEN = os.environ.get("TERABOX_CSRF_TOKEN", "")
TERABOX_BROWSER_ID = os.environ.get("TERABOX_BROWSER_ID", "")

DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB per chunk


class TeraboxDownloadError(Exception):
    """Dilempar kalau proses ambil link atau download Terabox gagal."""


def _cookies_configured() -> bool:
    return bool(TERABOX_NDUS and TERABOX_CSRF_TOKEN and TERABOX_BROWSER_ID)


async def _get_direct_link(share_url: str) -> dict:
    """
    Login ke Terabox pakai cookie akun sendiri, lalu ambil metadata + direct
    link dari sebuah share URL. Mengembalikan dict berisi filename, size, dan
    direct_url.
    """
    if not _cookies_configured():
        raise TeraboxDownloadError(
            "Cookie Terabox belum diatur. Set TERABOX_NDUS, TERABOX_CSRF_TOKEN, "
            "dan TERABOX_BROWSER_ID di config.env terlebih dahulu."
        )

    async with aiohttp.ClientSession() as session:
        client = TeraboxClient(
            session=session,
            cookies={
                "csrfToken": TERABOX_CSRF_TOKEN,
                "browserid": TERABOX_BROWSER_ID,
                "ndus": TERABOX_NDUS,
            },
        )
        try:
            await client.login()
            file_info = await client.get_share_info(share_url)
        except Exception as exc:  # noqa: BLE001 - dibungkus jadi error khusus
            raise TeraboxDownloadError(f"Gagal ambil info file Terabox: {exc}") from exc

        if not file_info or "direct_url" not in file_info:
            raise TeraboxDownloadError(
                "Tidak dapat menemukan direct link. Cek apakah link valid "
                "dan belum expired."
            )
        return file_info


async def download_terabox_file(share_url: str, download_dir: str) -> Path:
    """
    Entry point utama dipanggil dari listener/command bot.
    Mengunduh file dari share_url Terabox ke download_dir, mengembalikan
    Path lokal file yang sudah lengkap diunduh.
    """
    info = await _get_direct_link(share_url)
    filename = info.get("filename", "terabox_file")
    direct_url = info["direct_url"]

    Path(download_dir).mkdir(parents=True, exist_ok=True)
    local_path = Path(download_dir) / filename

    async with aiohttp.ClientSession() as session:
        async with session.get(direct_url) as resp:
            if resp.status != 200:
                raise TeraboxDownloadError(
                    f"Download gagal, server Terabox balas status {resp.status}"
                )
            with open(local_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(DOWNLOAD_CHUNK_SIZE):
                    f.write(chunk)

    return local_path


# ── Contoh integrasi command handler (Pyrogram) ──
#
# Tambahkan file ini di: bot/modules/terabox.py (di dalam repo MLTB)
# lalu daftarkan command-nya, misal di bot/modules/__init__.py atau file
# tempat command lain didaftarkan.
#
# from pyrogram import filters
# from pyrogram.types import Message
# from bot import bot
# from .terabox_helper import download_terabox_file, TeraboxDownloadError
#
# @bot.on_message(filters.command("terabox") & filters.private)
# async def terabox_leech(client, message: Message):
#     if len(message.command) < 2:
#         return await message.reply_text("Kirim: /terabox <link_share_terabox>")
#
#     share_url = message.command[1]
#     status_msg = await message.reply_text("Mengambil link & mendownload dari Terabox...")
#
#     try:
#         local_path = await download_terabox_file(share_url, "downloads/terabox")
#     except TeraboxDownloadError as e:
#         return await status_msg.edit_text(f"Gagal: {e}")
#
#     await status_msg.edit_text(f"Selesai diunduh: {local_path.name}\nMengunggah...")
#     # Panggil fungsi upload MLTB yang sudah ada (mirror ke gdrive / leech ke TG)
#     # sesuai command asal user, contoh:
#     # await upload_dir_or_file(local_path, message)


if __name__ == "__main__":
    # Uji cepat dari terminal: python terabox_helper.py <share_url>
    import sys

    if len(sys.argv) < 2:
        print("Usage: python terabox_helper.py <terabox_share_url>")
        raise SystemExit(1)

    result_path = asyncio.run(download_terabox_file(sys.argv[1], "downloads/terabox"))
    print(f"File tersimpan di: {result_path}")

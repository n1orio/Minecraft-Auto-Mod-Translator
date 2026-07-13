import json
import os
import re
import shutil
import time
import tkinter as tk
import zipfile
from tkinter import filedialog

from deep_translator import GoogleTranslator

# --- НАСТРОЙКИ ПО УМОЛЧАНИЮ ---
RP_NAME = "TranslatedModsPack"
PACK_FORMAT = 15
CHUNK_SIZE = 50
# ------------------------------


def choose_directory():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return filedialog.askdirectory(title="Выберите папку mods с вашими модами")


def cleanup_translation(text):
    if not isinstance(text, str):
        return text
    text = re.sub(r"%\s*(\d+)\s*\$\s*([sd])", r"%\1$\2", text)
    text = re.sub(r"%\s*([sd])", r"%\1", text)
    text = re.sub(r"§\s*([0-9a-fk-or])", r"§\1", text)
    text = re.sub(r"\\\s*n", r"\\n", text)
    return text


def parse_lang_file(content):
    data = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def build_lang_file(data):
    return "\n".join(f"{k}={v}" for k, v in data.items())


def create_rp_structure(target_dir):
    os.makedirs(target_dir, exist_ok=True)
    mcmeta = {
        "pack": {
            "pack_format": PACK_FORMAT,
            "description": "Auto Translator - Smart Mode",
        }
    }
    with open(os.path.join(target_dir, "pack.mcmeta"), "w", encoding="utf-8") as f:
        json.dump(mcmeta, f, indent=4, ensure_ascii=False)


def main():
    print("=== Auto Mod Translator (SMART MODE) ===")
    mods_folder = choose_directory()
    if not mods_folder:
        return

    print(f"Выбрана папка: {mods_folder}")
    rp_dir = os.path.join(os.path.dirname(mods_folder), RP_NAME)
    create_rp_structure(rp_dir)

    translator = GoogleTranslator(source="en", target="ru")
    mods_processed, mods_translated = 0, 0

    for filename in os.listdir(mods_folder):
        if not filename.endswith(".jar"):
            continue
        mods_processed += 1
        jar_path = os.path.join(mods_folder, filename)

        try:
            with zipfile.ZipFile(jar_path, "r") as jar:
                files = jar.namelist()
                en_files = [
                    f
                    for f in files
                    if re.search(r"lang/en_us\.(json|lang)$", f, re.IGNORECASE)
                ]

                for en_file in en_files:
                    is_json = en_file.lower().endswith(".json")

                    # 1. Читаем английский оригинал
                    with jar.open(en_file) as f:
                        content = f.read().decode("utf-8", errors="ignore")
                        if is_json:
                            try:
                                en_data = json.loads(content)
                            except:
                                continue
                        else:
                            en_data = parse_lang_file(content)

                    if not en_data:
                        continue

                    # 2. Ищем существующий русский файл (даже если он неполный)
                    ru_file_expected = re.sub(
                        r"en_us", "ru_ru", en_file, flags=re.IGNORECASE
                    )
                    existing_ru_data = {}

                    for f in files:
                        if f.lower() == ru_file_expected.lower():
                            with jar.open(f) as ru_f:
                                ru_content = ru_f.read().decode(
                                    "utf-8", errors="ignore"
                                )
                                if is_json:
                                    try:
                                        existing_ru_data = json.loads(ru_content)
                                    except:
                                        pass
                                else:
                                    existing_ru_data = parse_lang_file(ru_content)
                            break

                    # 3. УМНОЕ СРАВНЕНИЕ
                    ru_data = {}
                    keys_to_translate = []
                    values_to_translate = []

                    for k, v in en_data.items():
                        if not isinstance(v, str) or not v.strip():
                            ru_data[k] = v
                            continue

                        ru_val = existing_ru_data.get(k)

                        # Переводим, если: ключа нет, ИЛИ русский текст совпадает с английским (разраб схалтурил)
                        if ru_val is None or (
                            ru_val.strip() == v.strip() and re.search(r"[a-zA-Z]", v)
                        ):
                            keys_to_translate.append(k)
                            values_to_translate.append(v)
                        else:
                            # Оставляем существующий хороший перевод
                            ru_data[k] = ru_val

                    if not keys_to_translate:
                        print(f"[ПРОПУСК] {filename} — уже полностью переведен.")
                        continue

                    print(
                        f"[ПЕРЕВОД] {filename} — Найдено {len(keys_to_translate)} непереведенных строк..."
                    )

                    # 4. Батч-перевод только недостающих строк
                    for i in range(0, len(keys_to_translate), CHUNK_SIZE):
                        chunk_keys = keys_to_translate[i : i + CHUNK_SIZE]
                        chunk_values = values_to_translate[i : i + CHUNK_SIZE]

                        try:
                            translated = translator.translate_batch(chunk_values)
                        except Exception as e:
                            translated = []
                            for val in chunk_values:
                                try:
                                    translated.append(translator.translate(val))
                                except:
                                    translated.append(val)

                        for k, orig, trans in zip(chunk_keys, chunk_values, translated):
                            ru_data[k] = cleanup_translation(trans) if trans else orig

                        print(
                            f"  Прогресс: {min(i + CHUNK_SIZE, len(keys_to_translate))}/{len(keys_to_translate)} строк..."
                        )
                        time.sleep(0.5)

                    # 5. Сохраняем в ресурспак
                    out_file_name = (
                        ru_file_expected.lower()
                        if is_json
                        else re.sub(
                            r"en_us\.lang", "ru_RU.lang", en_file, flags=re.IGNORECASE
                        )
                    )
                    out_path = os.path.join(rp_dir, out_file_name)
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)

                    with open(out_path, "w", encoding="utf-8") as out_f:
                        if is_json:
                            json.dump(ru_data, out_f, indent=4, ensure_ascii=False)
                        else:
                            out_f.write(build_lang_file(ru_data))

                    mods_translated += 1
                    print(f"[УСПЕШНО] {filename} переведен!\n")

        except Exception as e:
            print(f"[ОШИБКА] {filename}: {e}")

    if mods_translated > 0:
        shutil.make_archive(rp_dir, "zip", rp_dir)
        print(f"\nГотово! Ресурспак '{RP_NAME}.zip' обновлен.")
    else:
        print("\nНовых переводов не потребовалось.")


if __name__ == "__main__":
    main()

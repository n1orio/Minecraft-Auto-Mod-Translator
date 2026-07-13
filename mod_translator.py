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
RP_NAME = "TranslatedModsPack"  # Название готового ресурспака
PACK_FORMAT = 15  # Формат ресурспака (15 = 1.20.x, 3 = 1.12.2)
CHUNK_SIZE = 50  # Количество строк для пакетного перевода за один раз
# ------------------------------


def choose_directory():
    """Открывает диалоговое окно для выбора папки mods"""
    root = tk.Tk()
    root.withdraw()  # Скрываем основное окно tkinter
    root.attributes("-topmost", True)
    folder_path = filedialog.askdirectory(title="Выберите папку mods с вашими модами")
    return folder_path


def cleanup_translation(text):
    """Исправляет сломанные Гуглом переменные Minecraft и коды цветов"""
    if not isinstance(text, str):
        return text
    # Исправляем позиционные переменные: % 1 $ s -> %1$s
    text = re.sub(r"%\s*(\d+)\s*\$\s*([sd])", r"%\1$\2", text)
    # Исправляем обычные переменные: % s -> %s, % d -> %d
    text = re.sub(r"%\s*([sd])", r"%\1", text)
    # Исправляем символы цвета: § a -> §a
    text = re.sub(r"§\s*([0-9a-fk-or])", r"§\1", text)
    # Исправляем переносы строк: \ n -> \n
    text = re.sub(r"\\\s*n", r"\\n", text)
    return text


def parse_lang_file(content):
    """Парсит старый формат .lang (для версий 1.12.2 и ниже)"""
    data = {}
    lines = content.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def build_lang_file(data):
    """Собирает словарь обратно в формат .lang"""
    return "\n".join(f"{k}={v}" for k, v in data.items())


def create_rp_structure(target_dir):
    """Создает pack.mcmeta для ресурспака"""
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    mcmeta = {
        "pack": {
            "pack_format": PACK_FORMAT,
            "description": "Автоматический перевод модов (Auto Translator)",
        }
    }
    with open(os.path.join(target_dir, "pack.mcmeta"), "w", encoding="utf-8") as f:
        json.dump(mcmeta, f, indent=4, ensure_ascii=False)


def main():
    print("=== Auto Mod Translator ===")
    print("Пожалуйста, выберите папку mods в открывшемся окне...")

    mods_folder = choose_directory()
    if not mods_folder:
        print("Папка не выбрана. Выход.")
        return

    print(f"Выбрана папка: {mods_folder}")
    rp_dir = os.path.join(os.path.dirname(mods_folder), RP_NAME)
    create_rp_structure(rp_dir)

    translator = GoogleTranslator(source="en", target="ru")

    mods_processed = 0
    mods_translated = 0

    for filename in os.listdir(mods_folder):
        if not filename.endswith(".jar"):
            continue

        mods_processed += 1
        jar_path = os.path.join(mods_folder, filename)

        try:
            with zipfile.ZipFile(jar_path, "r") as jar:
                files = jar.namelist()

                # Ищем en_us.json (новые версии) или en_US.lang (старые версии)
                en_files = [
                    f
                    for f in files
                    if re.search(r"lang/en_us\.(json|lang)$", f, re.IGNORECASE)
                ]

                for en_file in en_files:
                    is_json = en_file.lower().endswith(".json")
                    ru_file = re.sub(r"en_us", "ru_ru", en_file, flags=re.IGNORECASE)
                    ru_file_alt = re.sub(
                        r"en_US", "ru_RU", en_file
                    )  # Для .lang часто важен регистр

                    # Проверка наличия перевода в самом моде
                    if ru_file in files or ru_file_alt in files:
                        print(f"[ПРОПУСК] {filename} — русский перевод уже встроен.")
                        continue

                    print(
                        f"[ПЕРЕВОД] Начинаем перевод: {filename} ({'JSON' if is_json else 'LANG'})"
                    )

                    with jar.open(en_file) as f:
                        content = f.read().decode("utf-8", errors="ignore")
                        if is_json:
                            try:
                                en_data = json.loads(content)
                            except json.JSONDecodeError:
                                print(f"  [!] Ошибка чтения JSON, пропускаем.")
                                continue
                        else:
                            en_data = parse_lang_file(content)

                    if not en_data:
                        continue

                    keys = list(en_data.keys())
                    values = list(en_data.values())
                    ru_data = {}

                    # Пакетный перевод чанками (Batch translation)
                    for i in range(0, len(keys), CHUNK_SIZE):
                        chunk_keys = keys[i : i + CHUNK_SIZE]
                        chunk_values = values[i : i + CHUNK_SIZE]

                        to_translate = [
                            v if (isinstance(v, str) and v.strip()) else ""
                            for v in chunk_values
                        ]

                        try:
                            # Отправляем пачку строк в Google
                            translated = translator.translate_batch(to_translate)
                        except Exception as e:
                            print(
                                f"  [!] Ошибка чанка (API), переводим по одному... ({e})"
                            )
                            translated = []
                            for val in to_translate:
                                if val:
                                    try:
                                        translated.append(translator.translate(val))
                                    except:
                                        translated.append(val)
                                else:
                                    translated.append("")

                        # Собираем переведенный чанк обратно
                        for k, orig, trans in zip(chunk_keys, chunk_values, translated):
                            if not to_translate[
                                chunk_values.index(orig)
                            ]:  # Если была пустая строка
                                ru_data[k] = orig
                            else:
                                ru_data[k] = (
                                    cleanup_translation(trans) if trans else orig
                                )

                        print(
                            f"  Прогресс: {min(i + CHUNK_SIZE, len(keys))}/{len(keys)} строк..."
                        )
                        time.sleep(0.5)  # Пауза между чанками от бана IP

                    # Сохранение в ресурспак
                    out_path = os.path.join(rp_dir, ru_file.lower())
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)

                    with open(out_path, "w", encoding="utf-8") as out_f:
                        if is_json:
                            json.dump(ru_data, out_f, indent=4, ensure_ascii=False)
                        else:
                            out_f.write(build_lang_file(ru_data))

                    mods_translated += 1
                    print(f"[УСПЕШНО] Мод {filename} переведен!\n")

        except Exception as e:
            print(f"[ОШИБКА] Не удалось обработать мод {filename}: {e}")

    # Архивация в ZIP
    print(f"\nВсего обработано модов: {mods_processed}, переведено: {mods_translated}.")
    if mods_translated > 0:
        print(f"Сборка ресурспака {RP_NAME}.zip ...")
        shutil.make_archive(rp_dir, "zip", rp_dir)
        print(f"Готово! Ресурспак '{RP_NAME}.zip' создан рядом с вашей папкой mods.")
    else:
        print("Новых переводов не потребовалось, ресурспак не собран.")


if __name__ == "__main__":
    main()

import os
import re
import sys
# Эта библиотека (NBT) теперь должна быть установлена из форка
from nbt.region import RegionFile

# --- ПАРАМЕТРЫ, КОТОРЫЕ МОЖНО МЕНЯТЬ ---

ROOT_DIR = r"A:\Games\PrismLauncher\instances\БазаППЛ\minecraft\.bobby\play.pepeland.net"
OUTPUT_FILENAME = "minecraft_search_report.txt"

# --- УТИЛИТА ДЛЯ ИЗВЛЕЧЕНИЯ ID МИРА И ИЗМЕРЕНИЯ ---
def get_world_info(file_path):
    """Извлекает ID мира и имя измерения, предполагая структуру .../WorldID/Dimension/r.x.z.mca"""
    path_parts = file_path.split(os.sep)
    file_name = path_parts[-1]
    
    world_id = "UnknownID"
    dimension_name = "UnknownDimension"
    
    # 1. Измерение (Dimension Name) - папка перед файлом
    dimension_name = path_parts[-2] if len(path_parts) >= 2 else "UnknownDimension"
    
    # 2. ID мира (World ID) - папка перед измерением
    if len(path_parts) >= 3:
        potential_id = path_parts[-3]
        
        try:
            int(potential_id)
            world_id = potential_id
        except ValueError:
            if len(path_parts) >= 4:
                potential_id = path_parts[-4]
                try:
                    int(potential_id)
                    world_id = potential_id
                except ValueError:
                    pass
    
    # Защита от случая, когда ID не найдено
    if world_id == "UnknownID":
        if dimension_name.lower() in ['overworld', 'the_nether', 'the_end']:
             world_id = path_parts[-3] if len(path_parts) >= 3 else "UnknownID"
             if world_id.lower() in ['minecraft', 'region']:
                 world_id = path_parts[-4] if len(path_parts) >= 4 else "UnknownID"

    return world_id, dimension_name, file_name

# --- ФУНКЦИЯ ПОИСКА В ОДНОМ ФАЙЛЕ ---

def search_in_mca_file(file_path, target_text, search_pattern, report_writer):
    """
    Сканирует один MCA-файл на наличие указанного текста (обе стороны табличек) и возвращает список совпадений и список ошибок.
    """
    world_id, dimension_name, file_name = get_world_info(file_path)
    
    found_signs = []
    error_reports_file = []
    region = None
    
    try:
        region = RegionFile(file_path)
        
        for cx in range(32):
            for cz in range(32):
                
                try:
                    # Ожидаем, что форк NBT корректно читает MUTF-8
                    chunk = region.get_chunk(cx, cz)
                except Exception as e:
                    error_message = str(e)
                    
                    if "Chunk" in error_message and "not present" in error_message:
                        continue
                        
                    # Собираем остальные ошибки
                    region_match = re.search(r"r\.(-?\d+)\.(-?\d+)\.mca", file_name)
                    if region_match:
                         region_x = int(region_match.group(1))
                         region_z = int(region_match.group(2))
                         global_x_err = (region_x * 32) + cx
                         global_z_err = (region_z * 32) + cz
                    else:
                         global_x_err = 'N/A'
                         global_z_err = 'N/A'
                    
                    error_reports_file.append(
                        f"🛑 Чанк [{global_x_err}, {global_z_err}] в {world_id}/{dimension_name}/{file_name}: {e}"
                    )
                    continue 
                
                if chunk is None:
                    continue
                    
                root_tag = chunk if chunk.name != 'Level' else chunk['Level']
                
                if 'block_entities' in root_tag:
                    for entity in root_tag['block_entities']:
                        entity_id = str(entity.get('id', 'N/A'))
                        
                        if entity_id in ['minecraft:sign', 'minecraft:hanging_sign']:
                            
                            all_text = ""
                            raw_messages = []

                            # --- 1. СБОР ТЕКСТА С ПЕРЕДНЕЙ СТОРОНЫ ---
                            if 'front_text' in entity and 'messages' in entity['front_text']:
                                raw_messages.append("--- ПЕРЕДНЯЯ СТОРОНА ---")
                                for line_tag in entity['front_text']['messages']:
                                    line_content = line_tag.value
                                    
                                    # --- ИСПРАВЛЕНИЕ: Проверка на None ---
                                    if line_content is None:
                                        line_content = "" # Заменяем None на пустую строку
                                    # ------------------------------------
                                    
                                    all_text += line_content
                                    raw_messages.append(line_content)
                            
                            # --- 2. СБОР ТЕКСТА С ЗАДНЕЙ СТОРОНЫ ---
                            if 'back_text' in entity and 'messages' in entity['back_text']:
                                raw_messages.append("--- ЗАДНЯЯ СТОРОНА ---")
                                for line_tag in entity['back_text']['messages']:
                                    line_content = line_tag.value
                                    
                                    # --- ИСПРАВЛЕНИЕ: Проверка на None ---
                                    if line_content is None:
                                        line_content = "" # Заменяем None на пустую строку
                                    # ------------------------------------
                                    
                                    all_text += line_content
                                    raw_messages.append(line_content)
                                
                            
                            if search_pattern.search(all_text):
                                
                                entity_x = entity.get('x', 'N/A').value
                                entity_y = entity.get('y', 'N/A').value
                                entity_z = entity.get('z', 'N/A').value
                                
                                found_signs.append({
                                    'world_id': world_id,
                                    'dimension': dimension_name,
                                    'file': file_name,
                                    'type': entity_id,
                                    'x': entity_x,
                                    'y': entity_y,
                                    'z': entity_z,
                                    'text': '\n'.join(raw_messages)
                                })
        
    except Exception as e:
        # Эта ошибка (NoneType) больше не должна приводить к "КРИТИЧЕСКОЙ ОШИБКЕ ФАЙЛА"
        error_reports_file.append(f"❌ КРИТИЧЕСКАЯ ОШИБКА ФАЙЛА {world_id}/{dimension_name}/{file_name}: {e}")
        
    finally:
         if region is not None:
              region.close()
              
    return found_signs, error_reports_file

# --- ОСНОВНАЯ ФУНКЦИЯ ДЛЯ СКАНИРОВАНИЯ ВСЕХ ФАЙЛОВ ---

def multi_world_search(root_dir, target_text, output_file):
    """
    Рекурсивно ищет все .mca файлы, собирает результаты и выводит сводный отчет в файл.
    """
    
    with open(output_file, 'w', encoding='utf-8') as report_writer:
        
        def write_report(message, to_console=True):
            """Вспомогательная функция для вывода в консоль и записи в файл."""
            report_writer.write(message + "\n")
            if to_console:
                print(message)
                
        write_report("=" * 70)
        write_report(f"🔍 Запуск поиска '{target_text}' в директории: {root_dir}")
        write_report("--------------------------------------------------")

        search_pattern = re.compile(re.escape(target_text), re.IGNORECASE)
        
        total_mca_files = 0
        all_results = [] 
        all_errors = []
        
        for dirpath, dirnames, filenames in os.walk(root_dir):
            for filename in filenames:
                if filename.endswith(".mca"):
                    file_path = os.path.join(dirpath, filename)
                    
                    # Фильтруем файлы по папкам измерений
                    if 'overworld' in dirpath.lower() or 'the_nether' in dirpath.lower() or 'the_end' in dirpath.lower():
                        
                        path_parts = dirpath.lower().split(os.sep)
                        if not any(dim in path_parts for dim in ['overworld', 'the_nether', 'the_end']):
                             continue

                        total_mca_files += 1
                        
                        world_id, dimension_name, file_name = get_world_info(file_path)
                        
                        # Выводим информацию о сканируемом файле только в консоль, чтобы не перегружать отчет
                        print(f"--- Сканирование файла: {world_id}/{dimension_name}/{file_name}...", end='\r')
                        
                        found_list, error_list = search_in_mca_file(file_path, target_text, search_pattern, report_writer)
                        
                        all_results.extend(found_list)
                        all_errors.extend(error_list)
        
        # Очистка консоли после прогресса
        print(" " * 80, end='\r')

        write_report("\n" + "=" * 70, to_console=False)
        write_report(f"Поиск завершён!")
        write_report(f"  ➡️ Просканировано MCA-файлов: {total_mca_files}")
        write_report(f"  ➡️ Общее количество совпадений ('{target_text}'): **{len(all_results)}**")
        write_report(f"  ➡️ Отчет сохранен в файл: **{output_file}**")
        write_report("=" * 70, to_console=False)
        
        # --- ОТЧЕТ 1: ОШИБКИ ---
        if all_errors:
            write_report("\n*** ОТЧЕТ ОБ ОШИБКАХ ЧТЕНИЯ ЧАНКОВ (кроме 'Chunk not present') ***", to_console=False)
            for err in all_errors:
                write_report(err, to_console=False)
            write_report("--------------------------------------------------", to_console=False)

        # --- ОТЧЕТ 2: НАЙДЕННЫЕ ТАБЛИЧКИ ---
        if all_results:
            write_report("\n*** СВОДНЫЙ ОТЧЕТ: НАЙДЕННЫЕ ТАБЛИЧКИ ***", to_console=False)
            for i, res in enumerate(all_results):
                write_report("-" * 50, to_console=False)
                write_report(f"  НАХОДКА #{i+1}", to_console=False)
                write_report(f"  Мир (ID): **{res['world_id']}**", to_console=False)
                write_report(f"  Измерение/Файл: **{res['dimension']} / {res['file']}**", to_console=False)
                write_report(f"  Координаты: X:{res['x']}, Y:{res['y']}, Z:{res['z']} ({res['type']})", to_console=False)
                write_report("  Текст:", to_console=False)
                for line in res['text'].split('\n'):
                     write_report(f"    | {line}", to_console=False)
            write_report("-" * 50, to_console=False)
        else:
            write_report("\n*** Совпадений не найдено. ***", to_console=False)

# --- ЗАПУСК ---
if __name__ == "__main__":
    # 1. Ввод искомого слова
    target_text = input("Введите текст, который нужно найти на табличках: ")

    # 2. Запуск основного поиска
    multi_world_search(ROOT_DIR, target_text, OUTPUT_FILENAME)
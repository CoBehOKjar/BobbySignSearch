# The code is written entirely by AI.
import os
import re
import sys
import multiprocessing 
from concurrent.futures import ThreadPoolExecutor, as_completed

# This library (NBT) should be installed from the fork
# pip install git+https://github.com/OpenBagTwo/NBT.git
from nbt.region import RegionFile

# --- SCRIPT PARAMETERS ---
OUTPUT_FILENAME = "bobby_search_report.txt"

# --- UTILITY: GET WORLD INFO (No changes) ---
def get_world_info(file_path):
    """Extracts the World ID and Dimension Name, assuming a structure like .../WorldID/Dimension/r.x.z.mca"""
    path_parts = file_path.split(os.sep)
    file_name = path_parts[-1]
    
    world_id = "UnknownID"
    dimension_name = "UnknownDimension"
    
    # 1. Dimension Name - the folder right before the file
    dimension_name = path_parts[-2] if len(path_parts) >= 2 else "UnknownDimension"
    
    # 2. World ID - the folder before the dimension
    if len(path_parts) >= 3:
        potential_id = path_parts[-3]
        
        try:
            int(potential_id)
            world_id = potential_id
        except ValueError:
            # If it's not a number (e.g., "minecraft" or "region"), check one level higher
            if len(path_parts) >= 4:
                potential_id = path_parts[-4]
                try:
                    int(potential_id)
                    world_id = potential_id
                except ValueError:
                    pass
    
    # Failsafe for inconsistent directory structures
    if world_id == "UnknownID":
        if dimension_name.lower() in ['overworld', 'the_nether', 'the_end']:
             world_id = path_parts[-3] if len(path_parts) >= 3 else "UnknownID"
             if world_id.lower() in ['minecraft', 'region']:
                 world_id = path_parts[-4] if len(path_parts) >= 4 else "UnknownID"

    return world_id, dimension_name, file_name

# --- CORE FUNCTION: SEARCH MCA FILE (No changes) ---
def search_in_mca_file(file_path, target_text, search_pattern):
    """
    Scans a single MCA file for the target text (both sign sides)
    and returns a list of matches and a list of errors.
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
                    chunk = region.get_chunk(cx, cz)
                except Exception as e:
                    error_message = str(e)
                    
                    if "Chunk" in error_message and "not present" in error_message:
                        continue
                        
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
                        f"🛑 Chunk [{global_x_err}, {global_z_err}] in {world_id}/{dimension_name}/{file_name}: {e}"
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

                            # --- 1. GET FRONT TEXT ---
                            if 'front_text' in entity and 'messages' in entity['front_text']:
                                raw_messages.append("--- FRONT SIDE ---")
                                for line_tag in entity['front_text']['messages']:
                                    line_content = line_tag.value
                                    if line_content is None:
                                        line_content = "" 
                                    all_text += line_content
                                    raw_messages.append(line_content)
                            
                            # --- 2. GET BACK TEXT ---
                            if 'back_text' in entity and 'messages' in entity['back_text']:
                                raw_messages.append("--- BACK SIDE ---")
                                for line_tag in entity['back_text']['messages']:
                                    line_content = line_tag.value
                                    if line_content is None:
                                        line_content = ""
                                    all_text += line_content
                                    raw_messages.append(line_content)
                                
                            
                            # --- CHECK FOR MATCH ---
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
        error_reports_file.append(f"❌ CRITICAL FILE ERROR {world_id}/{dimension_name}/{file_name}: {e}")
        
    finally:
         if region is not None:
              region.close()
              
    return found_signs, error_reports_file


# --- MAIN FUNCTION (No changes to logic, only acceptance of thread count) ---

def multi_world_search(root_dir, target_text, output_file, max_threads):
    """
    Recursively searches all .mca files using multithreading, collects results, and writes a summary report.
    """
    
    # Open the report file (with utf-8 encoding)
    with open(output_file, 'w', encoding='utf-8') as report_writer:
        
        def write_report(message, to_console=True):
            """Helper function to write to both console and file."""
            report_writer.write(message + "\n")
            if to_console:
                print(message)
                
        write_report("=" * 70)
        write_report(f"🔍 Starting multithreaded search for '{target_text}' in directory: {root_dir}")
        write_report(f"⚡️ Using a maximum of **{max_threads}** worker threads.")
        write_report("--------------------------------------------------")

        # Compile regex pattern for case-insensitive search
        search_pattern = re.compile(re.escape(target_text), re.IGNORECASE)
        
        mca_files_to_scan = []
        
        # --- 1. COLLECT ALL FILES TO SCAN ---
        for dirpath, dirnames, filenames in os.walk(root_dir):
            if not any(dim in dirpath.lower() for dim in ['overworld', 'the_nether', 'the_end']):
                continue
                
            for filename in filenames:
                if filename.endswith(".mca"):
                    file_path = os.path.join(dirpath, filename)
                    mca_files_to_scan.append(file_path)

        total_mca_files = len(mca_files_to_scan)
        
        if total_mca_files == 0:
            write_report("\n*** WARNING: No .mca files found in dimension folders. Check ROOT_DIR. ***", to_console=True)
            return

        all_results = [] 
        all_errors = []
        
        # --- 2. EXECUTE THREADED SEARCH ---
        
        # Use ThreadPoolExecutor with the user-defined max_workers
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            
            # Map the function and its arguments (file_path, target_text, search_pattern) to the executor
            futures = {executor.submit(search_in_mca_file, file_path, target_text, search_pattern): file_path for file_path in mca_files_to_scan}
            
            processed_count = 0
            
            # Use as_completed to process results as soon as they are ready
            for future in as_completed(futures):
                
                file_path = futures[future]
                processed_count += 1
                
                world_id, dimension_name, file_name = get_world_info(file_path)
                
                # Update progress in console
                print(f"--- Processed {processed_count}/{total_mca_files} files. Current: {world_id}/{dimension_name}/{file_name}...", end='\r')
                
                try:
                    found_list, error_list = future.result()
                    all_results.extend(found_list)
                    all_errors.extend(error_list)
                except Exception as e:
                    # Catch any unexpected error that might happen during thread execution
                    all_errors.append(f"❌ UNEXPECTED THREAD ERROR processing {file_path}: {e}")

        # Clear the progress line from the console
        print(" " * 80, end='\r')

        # --- 3. WRITE FINAL SUMMARY ---
        write_report("\n" + "=" * 70, to_console=False) 
        write_report(f"🏆 SEARCH COMPLETE!")
        write_report(f"  ➡️ Scanned MCA files: {total_mca_files}")
        write_report(f"  ➡️ Total matches found ('{target_text}'): **{len(all_results)}**")
        write_report(f"  ➡️ Report saved to: **{output_file}**")
        write_report("=" * 70, to_console=False)
        
        # --- REPORT 1: ERRORS ---
        if all_errors:
            write_report("\n*** CHUNK READ ERROR REPORT (excluding 'Chunk not present') ***", to_console=False)
            for err in all_errors:
                write_report(err, to_console=False)
            write_report("--------------------------------------------------", to_console=False)

        # --- REPORT 2: MATCHES ---
        if all_results:
            write_report("\n*** SUMMARY REPORT: MATCHES FOUND ***", to_console=False)
            for i, res in enumerate(all_results):
                write_report("-" * 50, to_console=False)
                write_report(f"  MATCH #{i+1}", to_console=False)
                write_report(f"  World (ID): **{res['world_id']}**", to_console=False)
                write_report(f"  Dimension/File: **{res['dimension']} / {res['file']}**", to_console=False)
                write_report(f"  Coordinates: X:{res['x']}, Y:{res['y']}, Z:{res['z']} ({res['type']})", to_console=False)
                write_report("  Text:", to_console=False)
                for line in res['text'].split('\n'):
                     write_report(f"    | {line}", to_console=False)
            write_report("-" * 50, to_console=False)
        else:
            write_report("\n*** No matches found. ***", to_console=False)

# --- SCRIPT EXECUTION (Updated order of input) ---
if __name__ == "__main__":
    
    # 1. Determine default thread count
    default_threads = multiprocessing.cpu_count()

    # 2. Get the thread count from the user (FIRST INPUT)
    while True:
        thread_input = input(f"Enter the number of threads (Recommended: {default_threads}, or x2 if fast SSD. press Enter for default): ")
        if not thread_input:
            max_threads = default_threads
            print(f"Using default thread count: {max_threads}")
            break
        try:
            max_threads = int(thread_input)
            if max_threads < 1:
                print("Please enter a positive number.")
            else:
                break
        except ValueError:
            print("Invalid input. Please enter a number.")

    # 3. Get the server root folder path (SECOND INPUT)
    print("\n---")
    print("Please provide the path to the server's root folder.")
    print(r"Example: C:\PrismLauncher\instances\thebestmodpack\minecraft\.bobby\play.pepeland.net")
    root_dir_input = input("Enter path: ")
    
    # Validate the path
    if not os.path.isdir(root_dir_input):
        print(f"Error: Path not found or is not a directory: {root_dir_input}")
        sys.exit() # Exit the script

    # 4. Get the search term
    target_text = input("Enter the text to search for on signs: ")

    # 5. Run the main search function
    multi_world_search(root_dir_input, target_text, OUTPUT_FILENAME, max_threads)
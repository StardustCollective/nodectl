from os import stat, path, remove, listdir, cpu_count
from pathlib import Path
from time import sleep
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed, wait as thread_wait


def process_snap_files(files,snapshot_dir,log):
    result = {}
    for snap_hash_name in files:
        file_path = path.join(snapshot_dir, str(snap_hash_name))

        try:
            inode = stat(file_path).st_ino
            if inode not in result:
                result[inode] = []
            if snap_hash_name not in result[inode]:
                result[inode].append(snap_hash_name)

        except Exception as e:
            log.logger.warn(f"snaphost --> Error processing file {snap_hash_name}: {e}")
    
    return result


def merge_snap_results(dicts,debug=False):
    merged = {}
    results = {
        "match_count": 0,
        "solo_count": 0,
        "ord_count": 0,
        "hash_count": 0,
        "ord_lowest": -1,
        "ord_highest": -1,
        "other": 0
    }
    example_snaps = []
    example_hashes = []

    for d in dicts:
        for inode, inode_list in d.items():
            if inode not in merged:
                merged[inode] = []
            for snap_hash in inode_list:
                if snap_hash not in merged[inode]:
                    merged[inode].append(snap_hash)

    for _ , snap_hash in merged.items(): 
        # for inode, snap_hash in dicts.items():         
        if len(snap_hash) > 1:
            results["match_count"] += 1
        elif len(snap_hash) > 0:
            if len(snap_hash[0]) < 64 and snap_hash[0].isdigit():
                if debug and len(example_snaps) < 11:
                    example_snaps.append(snap_hash[0])
                if int(snap_hash[0]) < results["ord_lowest"] or results["ord_lowest"] < 0:
                    # find lowest break point
                    results["ord_lowest"] = int(snap_hash[0])
            elif len(snap_hash[0]) > 63:
                if debug and len(example_hashes) < 11:
                    example_hashes.append(snap_hash[0])
            results["solo_count"] += 1
        else:
            results["other"] += 1

        for i in snap_hash:
            if len(i) < 64 and i.isdigit():
                if int(i) > results["ord_highest"]:
                    # find highest ordinal
                    results["ord_highest"] = int(i)
                results["ord_count"] += 1
            elif len(i) > 63:
                results["hash_count"] += 1
            else:
                results["other"] += 1
    
    if debug:
        print('=============================')
        for n in [example_snaps,example_hashes]:
            for i in n:
                print(i)

    return merged, results


def clean_info(snapshot_info_dir, functions, log, start,end):
    for current_snap in range(start,end):
        info_path = path.join(snapshot_info_dir, str(current_snap))
        if path.isfile(info_path):
            functions.print_cmd_status({
                "text_start": "Handling",
                "brackets": "ordinal",
                "text_end": "info bookmark",
                "status": path.split(info_path)[1],
                "status_color": "red",
                "newline": True,
            })
            log.logger.warn(f"remove_snapshots --> removing snapshot {info_path}")
            remove(info_path)


def remove_elements(i_node_dict,snapshot_dir, functions, log, start):
    for _ , match_list in i_node_dict.items():
        test_range = True if len(match_list) > 1 else False
        skip = False
        
        for snap_hash in match_list:
            if test_range:
                for i_snap in match_list:
                    if len(i_snap) < 63:
                        if int(i_snap) < start:
                            skip = True

            if skip: 
                continue

            snap_to_remove = path.join(snapshot_dir,snap_hash)
            if snap_hash.isdigit():
                snapshot_display = snap_hash
            if len(snap_hash) > 63:
                snapshot_display = f"{snap_hash[0:8]}....{snap_hash[-8:]}"

            functions.print_cmd_status({
                "text_start": "Removing",
                "brackets": "ordinal_elements",
                "status": snapshot_display,
                "status_color": "red",
                "newline": True,
            })
            log.logger.warn(f"remove_snapshots --> removing ordinal {snap_to_remove}")
            remove(snap_to_remove)


def print_report(count_results,functions):
    functions.print_cmd_status({
        "text_start": "Valid chain ordinals",
        "status": f'{count_results["match_count"]:,}',
        "status_color": "green",
        "newline": True,
    })
    functions.print_cmd_status({
        "text_start": "Broken chain ordinals",
        "status": f'{count_results["solo_count"]:,}',
        "status_color": "red",
        "newline": True,
    })
    functions.print_cmd_status({
        "text_start": "Ordinals count",
        "status": f'{count_results["ord_count"]:,}',
        "status_color": "yellow",
        "newline": True,
    })
    functions.print_cmd_status({
        "text_start": "Hash count",
        "status": f'{count_results["hash_count"]:,}',
        "status_color": "yellow",
        "newline": True,
    })

    print("")

    functions.print_cmd_status({
        "text_start": "Start removing ordinal",
        "status": count_results["ord_lowest"],
        "status_color": "yellow",
        "newline": True,
    })
    functions.print_cmd_status({
        "text_start": "End removing ordinal",
        "status": count_results["ord_highest"],
        "status_color": "yellow",
        "newline": True,
    })


def discover_snapshots(snapshot_dir, functions, log):
    with ThreadPoolExecutor() as executor:
        functions.status_dots = True
        status_obj = {
            "text_start": f"Analyze Node chain",
            "status": "running",
            "status_color": "yellow",
            "dotted_animation": True,
            "newline": False,
            "timeout": False,
        }
        _ = executor.submit(functions.print_cmd_status,status_obj)

        files = [f for f in listdir(snapshot_dir) if path.isfile(path.join(snapshot_dir, f))]
        num_workers = cpu_count()
        chunk_size = len(files) // num_workers
        length_of_files = len(files)

        functions.status_dots = False
        functions.print_cmd_status({
            "text_start": "Found on Node",
            "brackets": f"{length_of_files:,}",
            "text_end": "inc files",
            "status": "completed",
            "status_color": "green",
            "dotted_animation": False,
            "newline": True,
        })

    with ThreadPoolExecutor() as executor:
        functions.status_dots = True
        status_obj = {
            "text_start": f"Discovering Node ordinals",
            "status": "running",
            "status_color": "yellow",
            "dotted_animation": True,
            "newline": False,
            "timeout": False,
        }
        _ = executor.submit(functions.print_cmd_status,status_obj)

        with ProcessPoolExecutor(max_workers=num_workers) as executor2:
            futures = []
            for i in range(0, length_of_files, chunk_size):
                file_chunk = files[i:i + chunk_size]
                futures.append(executor2.submit(process_snap_files, file_chunk, snapshot_dir, log))
            results = [future.result() for future in as_completed(futures)]

        functions.status_dots = False
        functions.print_cmd_status({
            "text_start": "Ordinal analysis process",
            "status": "completed",
            "status_color": "green",
            "dotted_animation": False,
            "newline": True,
        })

    return results
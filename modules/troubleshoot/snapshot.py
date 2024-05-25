from os import stat, path, remove, listdir, cpu_count
from time import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed, wait as thread_wait
from termcolor import colored, cprint
from datetime import datetime

def process_snap_files(files, snapshot_dir, log, find_inode):
    result = {}
    for ord_hash_name in files:
        file_path = path.join(snapshot_dir, str(ord_hash_name))

        try:
            inode = stat(file_path).st_ino
            file_mtime = path.getmtime(file_path)
            if inode not in result:
                if find_inode and inode != find_inode:
                    continue
                result[inode] = {
                    "inode": [],
                    "stamp": [],
                } 
            if ord_hash_name not in result[inode]["inode"]:
                if find_inode and inode != find_inode:
                    continue
                result[inode]["inode"].append(ord_hash_name)
            if file_mtime not in result[inode]["stamp"]:
                if find_inode and inode != find_inode:
                    continue
                result[inode]["stamp"].append(file_mtime)

        except Exception as e:
            log.logger.warn(f"snaphost --> Error processing file {ord_hash_name}: {e}")
    
    return result


def set_count_dict():
    return {
        "length_of_files": 0,
        "match_count": 0,
        "solo_count": 0,
        "ord_count": 0,
        "hash_count": 0,
        "unmatched_time": 0,
        "day_0_old": 0,
        "day_10_old": 0,
        "day_20_old": 0,
        "day_30_old": 0,
        "day_60_old": 0,
        "other": 0,
        "ord_lowest": -1,
        "ord_highest": -1,
    }


def merge_snap_results(matches,functions,log,debug=False):
    merged = {}
    results = set_count_dict()
    results["length_of_files"] = matches["length_of_files"]
    matches = matches["results"]
    example_snaps = []
    example_hashes = []
    days = [0,10,20,30,60]

    with ThreadPoolExecutor() as executor:
        functions.status_dots = True
        status_obj = {
            "text_start": f"Compiling results",
            "status": "running",
            "status_color": "yellow",
            "dotted_animation": True,
            "newline": False,
            "timeout": False,
        }
        _ = executor.submit(functions.print_cmd_status,status_obj)

        try:
            for d in matches:
                for inode, inode_list in d.items():
                    if inode not in merged:
                        merged[inode] = {
                            "inode": [],
                            "stamp": [],
                        }
                    for ktype, ord_hash_stamp_list in inode_list.items():
                        for ord_hash_stamp in ord_hash_stamp_list:
                            if ktype == "inode":
                                if ord_hash_stamp not in merged[inode][ktype]:
                                    merged[inode][ktype].append(ord_hash_stamp)
                                if len(merged[inode][ktype]) > 1: # make sure oridnal is the first element
                                    merged[inode][ktype] = sorted(merged[inode][ktype], key=lambda x: (len(x) >= 64, x))
                            if ktype == "stamp":
                                if ord_hash_stamp not in merged[inode][ktype]:
                                    merged[inode][ktype].append(ord_hash_stamp)
        except Exception as e:
            log.logger.error(f"snapshot --> error matching during process of compiling snapshot results | [{e}]")

        del matches # cleanup memory
        try:
            for _ , ord_hash_stamp in merged.items(): 
                ord_hash = ord_hash_stamp["inode"]

                if len(ord_hash) > 1:
                    results["match_count"] += 1
                elif len(ord_hash) > 0:
                    if len(ord_hash[0]) < 64 and ord_hash[0].isdigit():
                        if debug and len(example_snaps) < 11:
                            example_snaps.append(ord_hash[0])
                        if int(ord_hash[0]) < results["ord_lowest"] or results["ord_lowest"] < 0:
                            # find lowest break point
                            results["ord_lowest"] = int(ord_hash[0])
                    elif len(ord_hash[0]) > 63:
                        if debug and len(example_hashes) < 11:
                            example_hashes.append(ord_hash[0])
                    results["solo_count"] += 1
                else:
                    results["other"] += 1

                for i in ord_hash:
                    if len(i) < 64 and i.isdigit():
                        if int(i) > results["ord_highest"]:
                            # find highest ordinal
                            results["ord_highest"] = int(i)
                        results["ord_count"] += 1
                    elif len(i) > 63:
                        results["hash_count"] += 1
                    else:
                        results["other"] += 1

                if len(ord_hash_stamp["stamp"]) > 1:
                    results["unmatched_time"] += 1
                for i in ord_hash_stamp["stamp"]:
                    for t in days:
                        if i < (time() - (t*86400)):
                            results[f"day_{t}_old"] += 1
        except Exception as e:
            log.logger.error(f"snapshot --> error counting compiled snapshot data | [{e}]")  

        for i, t in enumerate(days[:-1]):
            results[f"day_{t}_old"] -= results[f"day_{days[i+1]}_old"]

        functions.status_dots = False
        functions.print_cmd_status({
            "text_start": f"Compiling results",
            "status": "completed",
            "status_color": "green",
            "dotted_animation": False,
            "newline": True,
        })
        
    if debug:
        print('  =============================')
        for n in [example_snaps,example_hashes]:
            for i in n:
                print(f"  {i}")

    return merged, results


def print_count(count,functions):
    functions.print_cmd_status({
        "text_start": "Found and removed",
        "status": str(count),
        "status_color": "yellow",
        "newline": True,
    })


def clean_info(snapshot_info_dir, functions, log, inode_dict, start,end, old_days, debug):
    count = 0
    for current_snap in range(start,end):
        info_path = path.join(snapshot_info_dir, str(current_snap))
        if path.isfile(info_path):
            count += 1
            functions.print_cmd_status({
                "text_start": "Handling",
                "brackets": "ordinal",
                "text_end": "info bookmark",
                "status": path.split(info_path)[1],
                "status_color": "red",
                "newline": True,
            })
            log.logger.warn(f"snaphost --> removing snapshot {info_path}")
            if not debug: 
                remove(info_path)

    if count > 0:
        print_count(count,functions)
    
    if old_days > 0:
        count = 0
        threshold_time = time() - (old_days*86400) 
        for match_list in inode_dict.values():
            snap_list = match_list['inode']
            time_list = match_list['stamp']
            for i, ord_snap in enumerate(snap_list):
                try: stamp = time_list[i]
                except: pass # only one timestamp
                if stamp < threshold_time:       
                    if len(ord_snap) < 64:
                        info_path = path.join(snapshot_info_dir, str(ord_snap))
                        if path.isfile(info_path):
                            count += 1
                            functions.print_cmd_status({
                                "text_start": "Handling old",
                                "brackets": "ordinal",
                                "text_end": "info bookmark",
                                "status": path.split(info_path)[1],
                                "status_color": "red",
                                "newline": True,
                            })
                            log.logger.warn(f"snaphost --> removing snapshot {info_path}")
                            if not debug: 
                                remove(info_path)
        if count > 0:
            print_count(count,functions)


def remove_elements(inode_dict, snapshot_dir, functions, log, start, old_days, debug=False):
    count, range_count, old_count = 0, 0, 0

    for _ , match_list in inode_dict.items():
        skip = False

        snap_list = match_list['inode']
        time_list = match_list['stamp']
        test_range = True if len(snap_list) > 1 else False
        threshold_time = time() - (old_days*86400)
        oe = "oridinal element"
        for i, ord_hash in enumerate(snap_list):
            if test_range and len(ord_hash) < 63:
                try: stamp = time_list[i]
                except: pass # only one timestamp
                if old_days > 0 and stamp < threshold_time: # -1 is disabled
                        old_count += 2
                        oe = "old ordinal element"
                        log.logger.warn(f"snapshot --> remove old snaps requested [{old_days}] - found old snap or ordinal [{ord_hash}] that will be removed.")  
                elif int(ord_hash) < start:
                    skip = True
                else:
                    range_count += 2

            if skip: 
                continue

            snap_to_remove = path.join(snapshot_dir,ord_hash)
            if ord_hash.isdigit():
                snapshot_display = ord_hash
            if len(ord_hash) > 63:
                snapshot_display = f"{ord_hash[0:8]}....{ord_hash[-8:]}"

            functions.print_cmd_status({
                "text_start": "Removing",
                "brackets": oe,
                "status": snapshot_display,
                "status_color": "red",
                "newline": True,
            })
            log.logger.warn(f"snapshot --> removing ordinal {snap_to_remove}")
            count += 1
            if not debug: 
                remove(snap_to_remove)

    for n in range(3,0,-1):
        if n > 2:
            if old_days > 0:
                old_str = colored(str(old_days),"yellow")
                end_str = colored("] days................","cyan")
                d_str = colored(f"snapshots older than [{old_str}{end_str}","cyan")
                d_str = f"Snapshots older than [{old_str}{end_str}"
                c = old_count
            else:
                continue
        elif n > 1:
            if old_days < 1: continue # not needed unless old_days is requested
            d_str = "snapshots from requested range"
            c = range_count
        else:
            d_str = "Total snapshots"
            c = count

        functions.print_cmd_status({
            "text_start": d_str,
            "newline": True,
        })
        print_count(c,functions)


def print_report(count_results,fix,functions):
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

    print("")

    functions.print_cmd_status({
        "text_start": f"Chain elements <",
        "brackets": "10",
        "text_end": "days old",
        "status": count_results["day_0_old"],
        "status_color": "yellow",
        "newline": True,
    })

    for t in ["10","20","30","60"]:
        functions.print_cmd_status({
            "text_start": "Chain elements >",
            "brackets": t,
            "text_end": "days old",
            "status": count_results[f"day_{t}_old"],
            "status_color": "yellow",
            "newline": True,
        })

    if count_results["old_days"] > 0 and fix:
        functions.print_cmd_status({
            "text_start": "Remove ordinals > than",
            "status": f'{count_results["old_days"]} Days',
            "status_color": "yellow",
            "newline": True,
        })


def discover_snapshots(snapshot_dir, functions, log, inode=False):
    return_results = {
        "results": None,
        "valid": False,
        "length_of_files": 0,
        "max_ordinal": -1,
    }
    files = []
    max_ord = -1

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

        # files = [f for f in listdir(snapshot_dir) if path.isfile(path.join(snapshot_dir, f))]
        for ordhash in listdir(snapshot_dir):
            if path.isfile(path.join(snapshot_dir, ordhash)):
                files.append(ordhash)
                try:
                    if len(ordhash) < 64 and int(ordhash) > max_ord:
                        max_ord = int(ordhash)
                except Exception as e:
                    log.logger.error(f"unable to determine snapshot data type, skipping [{ordhash}]")

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

    if length_of_files < 1:  
        return return_results

    with ThreadPoolExecutor() as executor:
        functions.status_dots = True
        status_obj = {
            "text_start": f"Discovering Node snapshots",
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
                futures.append(executor2.submit(process_snap_files, file_chunk, snapshot_dir, log, inode))
            results = [future.result() for future in as_completed(futures)]

        results = [d for d in results if d] # remove all empty dictionaries

        functions.status_dots = False
        functions.print_cmd_status({
            "text_start": "Ordinal analysis process",
            "status": "completed",
            "status_color": "green",
            "dotted_animation": False,
            "newline": True,
        })

    return_results["results"] = results
    return_results["valid"] = True
    return_results["length_of_files"] = length_of_files
    return_results["max_ordinal"] = max_ord
    return return_results


def custom_input(start,end,functions):
    while True:
        user_start = input(f'{colored("  start ordinal [","magenta")}{start}{colored("]: ","magenta")}')
        if user_start.lower() == "q":
            cprint("  Action cancelled by Node Operator","green")
            return
        elif user_start != "" and user_start != None:
            try:
                user_start = int(user_start)
            except:
                cprint("  Invalid starting point, try again","red")
            else:
                if user_start == end or user_start > end:
                    functions.print_paragraphs([
                        ["Invalid starting ordinal.",1,"red"],
                        ["The start value cannot be greater than or equal to the end value.",1,"red"],
                    ])
                else:
                    break
        else:
            break

    start = user_start
    for n, s_t in enumerate(["start","stop"]):
        functions.print_cmd_status({
            "text_start": f"Requested {s_t} ordinal",
            "status": str(start) if n < 1 else str(end),
            "status_color": "yellow",
            "newline": True,
        })

    return start, end


def ordhash_to_ordhash(results,ordhashtype):
    for result in results["results"]:
        for ordhash_dict in result.values():
            stamp = ordhash_dict["stamp"]
            for ordhash in ordhash_dict["inode"]:
                if ordhashtype == "ordinal":
                    if len(ordhash) > 63:
                        return ordhash, stamp
                else:
                    if len(ordhash) < 63:
                        return ordhash, stamp

                    
def print_single_ordhash(profile,ordinal,hash,ordhash_inode,stamp,functions):
    issue = True if len(stamp) > 1 else False
    print_stamps = []
    for m_stamp in stamp:
        dt = datetime.fromtimestamp(m_stamp)
        print_stamps.append(dt.strftime('%Y-%m-%d %H:%M:%S'))

    print_out_list = [
        {
            "header_elements" : {
                "PROFILE": profile,
            },
        },
        {
            "header_elements" : {
                "INODE LINK": ordhash_inode,
                "ORDINAL": ordinal,
                "DATE": print_stamps[0] if not issue else "invalid_link",
            },
        },
        {
            "header_elements" : {
                "HASH": hash,
            },
        },
    ]
    
    for header_elements in print_out_list:
        functions.print_show_output({
            "header_elements" : header_elements
        })     

    if issue:
        functions.print_paragraphs([
            ["",1],[" WARNING ",0,"yellow,on_red"], ["There may be an invalid chain on this Node.",0,"red"],
            ["The file time/date stamps do not match.",2,"red"]
        ])
        for i, p_date in enumerate(print_stamps):
            ordhash_str = colored(p_date,"red")
            title = "Ordinal Date:" if i < 1 else "Hash Date:"
            title = colored(title,"cyan")
            print(f"  {title} {ordhash_str}")

    print("")
    return
                

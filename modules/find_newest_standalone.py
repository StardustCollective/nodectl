from os import walk, path

def find_newest(data_path):
    f_time, f_newest = 0, None
    error_msg = False
    
    for root, _, files in walk(data_path):
        for file in files:
            file_path = path.join(root, file)
            try:
                creation_time = path.getctime(file_path)
                if creation_time > f_time:
                    f_time = creation_time
                    f_newest = file_path
            except OSError as e:
                error_msg = f"cli_node_last_snapshot -> Error accessing {file_path}: {e}"

    return f_time, f_newest, error_msg
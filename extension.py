import os
import shutil, re
import vscode
from math import inf
from datetime import datetime, timedelta

ext = vscode.Extension(name = "LFS", display_name = "Large File Sort", version = "1.0.0")


def print_progress_bar(prefix, percent, text):
    percent_text = '{:.2f}'.format(percent)
    status_text = f'\r{prefix} {percent_text}% {text}'
    vscode.window.set_status_bar_message(f"{ext.name}: {status_text}", 30)


def progress_prefix(text = ''):
  return '[{}] {}'.format(datetime.now().strftime('%H:%M:%S'), text)


def filesize_humanize(size):
    prefix = ["", "K", "M", "G", "T", "P", "E", "Z", "Y"]
    i = 0
    while size >= 1024:
        size /= 1024
        i += 1
    t = "{:.2f}".format(size)
    while t[-1] == '0': t = t[:-1]
    if t[-1] == '.': t = t[:-1]
    return t + " " + prefix[i] + "B"


def open_utf8(name, mode):
    return open(name, mode, encoding='utf-8')


def sort_single(fname):
    with open_utf8(fname, 'r') as f:
        data = sorted(f.readlines())
    with open_utf8(fname, 'w') as f:
        f.writelines(data)
    return fname


def run(filename):
    result = None

    basename = os.path.basename(filename)
    TMP_DIR_PAT = f'{filename}-merge.tmp'
    TMP_DIR = TMP_DIR_PAT
    for _ in range(100):
        if not os.path.isdir(TMP_DIR): break
        TMP_DIR = f'{TMP_DIR_PAT}{_}'
    os.mkdir(TMP_DIR)

    try:
        # create information
        seg = {}
        filesize = 0
        percent = 0
        time = datetime.now()
        with open_utf8(filename, 'r') as f:
            pidx = 0
            while True:
                # ui update
                if time + timedelta(milliseconds=500) < datetime.now():
                    time = datetime.now()
                    pidx = (pidx + 1) % 3
                    text = 'read {}'.format(filesize_humanize(filesize)) + '.' * ((pidx % 3) + 1)
                    print_progress_bar(basename, percent, text)

                # file processing
                s = f.readline()
                if not s: break
                words = s.strip()
                if len(words) == 0: continue
                c = ord(s[0])
                size = len(s) * 4 - len(words)
                if c not in seg: seg[c] = 0
                seg[c] += size
                filesize += size

        # ui update
        print_progress_bar(basename, 0, 'calculating...')

        # calculate size of each segment
        ch2buc = {}
        buc_size = 0
        buc_limit = 128 * (1024 ** 2) # 128 MB
        buc_index = 0
        for idx, size in sorted(seg.items()):
            buc_size += size
            if buc_size < buc_limit:
                ch2buc[idx] = buc_index
                continue
            ch2buc[idx] = buc_index
            buc_size = 0
            buc_index += 1

        fseg_name = [f'{TMP_DIR}/{i}' for i in range(buc_index + 1)]

        # read and save into segment
        with open_utf8(filename, 'r') as f:
            fseg = [open_utf8(name, 'w') for name in fseg_name]

            # divide
            cur_size = 0
            while True:
                # file processing
                s = f.readline()
                if not s: break
                words = s.strip()
                if len(words) == 0: continue
                cur_size += len(s) * 4 - len(words)
                fseg[ch2buc[ord(s[0])]].write(s)

                # ui update (~ 50%)
                if time + timedelta(milliseconds=500) < datetime.now():
                    time = datetime.now()
                    pidx = (pidx + 1) % 3
                    percent = (cur_size / filesize) * 50
                    print_progress_bar(basename, percent, 'processing.' + '.' * (pidx % 3))

            # conquer
            for i, fs in enumerate(fseg):
                fs.close()
                sort_single(fs.name)
                # ui update (50% ~ 80%)
                percent = 50 + (i / len(fseg)) * 30
                text = 'sorting ({}/{})'.format(i + 1, len(fseg))
                print_progress_bar(basename, percent, text)

        os.remove(filename)

        vscode.window.show_info_message(f"{ext.name}: '${filename}' Almost done, Do not turn off")

        # append each segment to output
        with open_utf8(filename, 'w') as fout:
            for i, name in enumerate(fseg_name):
                fseg = open_utf8(name, 'r')
                fout.writelines(fseg.readlines())
                fseg.close()
                os.remove(name)

                # ui update (80% ~)
                percent = 80 + (i / len(fseg_name)) * 20
                text = 'merging ({}/{})'.format(i + 1, len(fseg_name))
                print_progress_bar(basename, percent, text)
        print_progress_bar(basename, 100, 'finished')
    except Exception as e:
        result = e
    finally:
        if os.path.isdir(TMP_DIR):
            shutil.rmtree(TMP_DIR)
    return result


def list_files(start_path, ignore_patterns=[]):
    ign_pat = []
    for pat in ignore_patterns:
        ign_pat.append(pat.replace('\\', '/'))
        ign_pat.append(pat.replace('/', '\\'))
    ign_pat = list(map(lambda x: x.replace('.', '\\.').replace('*', '.*'), ign_pat))
    ignores = re.compile('|'.join(ign_pat))
    paths = []
    for root, dirs, files in os.walk(start_path):
        if re.search(ignores, root): continue
        for f in files:
            cur = f'{root}\\{f}'
            if not re.search(ignores, cur):
                paths.append(cur)
    return paths


def search(root_dir):
    options = vscode.ext.QuickPickOptions(
        title='Which file you want to sort?',
        match_on_detail=True,
        can_pick_many=False
    )
    ignores = [
        '**/.git'
    ]
    filelist = list_files(root_dir, ignore_patterns=ignores)
    data = list(map(
        lambda path: vscode.ext.QuickPickItem(path, None, filesize_humanize(os.path.getsize(path))),
        filelist
    ))
    selected = vscode.window.show_quick_pick(data, options)
    if not selected or isinstance(selected, str):
        return selected
    if isinstance(selected, vscode.types.QuickPickItem):
        return selected.label
    return None


def has_disk_freespace(filepath):
    total, used, free = shutil.disk_usage(filepath)
    print("total", filesize_humanize(total))
    print("used", filesize_humanize(used))
    print("free", filesize_humanize(free))
    filesize = os.path.getsize(filepath)
    print("filesize", filesize_humanize(filesize))
    return free >= filesize + 1024 ** 2  # 1 MB


@ext.event
def on_activate():
    return f"The Extension '{ext.name}' has started"


@ext.command(title="Sort File", category=ext.name)
def sort_file():
    options = vscode.types.WorkspaceFolderPickOptions(
        ignore_focus_out=True,
        placeholder='Select workspace for searching file...')
    folder = vscode.window.show_workspace_folder_pick(options=options)
    if folder:
        filename = search(folder['uri']['fsPath'])
        if filename:
            return_str = ''
            if has_disk_freespace(filename):
                error = run(filename)
                if error:
                    return_str = str(error)
                else:
                    return_str = f"'{filename}' sorted."
            else:
                return_str = 'Not enough free disk space for sort.'
            return vscode.window.show_info_message(f"{ext.name}: {return_str}")
    return None


vscode.build(ext)

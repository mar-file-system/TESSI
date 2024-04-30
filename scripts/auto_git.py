#! /usr/bin/env python3.8

import argparse
import git
import logging
import os
import subprocess
import sys

def setup_logger(verbose, logfile):
    # Create a logger
    logger = logging.getLogger(__file__)
    logger.setLevel(logging.DEBUG)  # Capture all levels to the logger

    # Create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Optionally add a file handler
    if logfile:
        fh = logging.FileHandler(logfile)
        fh.setLevel(logging.DEBUG)  # Log everything to file
        logger.addHandler(fh)

    # Create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    if logfile:
        fh.setFormatter(formatter)

    # Add console handler to logger
    logger.addHandler(ch)

    return logger


def get_last_commit(repo, file_path):
    logger = logging.getLogger(__file__)
    commits = list(repo.iter_commits(paths=file_path, max_count=1))
    if commits:
        last = commits[0].hexsha
        ts   = commits[0].committed_date
    else:
        last = None
        ts   = None
    logger.debug(f"Last commit for {file_path.split('/')[-1]}: {last[-5:]} {ts}")
    return last,ts

# search all files in a directory to see if a particular commit is present
def commit_is_newer(repo, dirpath, test_file_path, target_commit_ts):
    logger = logging.getLogger(__file__)

    if not target_commit_ts:
        logger.debug(f"No need to test {test_file_path}; not yet committed")
        return False

    if os.path.isdir(dirpath):
        latest_commit_ts = None
        for f in os.listdir(dirpath):
            commit,ts = get_last_commit(repo, os.path.join(dirpath,f))
            if ts and (not latest_commit_ts or ts > latest_commit_ts):
                latest_commit_ts = ts
        if not latest_commit_ts:
            logger.debug(f"Need to test {test_file_path}: no test results yet committed")
            return True
        if latest_commit_ts > target_commit_ts:
            logger.debug(f"No need to test {test_file_path}: most recent test results already committed")
            return False
        else:
            logger.debug(f"Need to test {test_file_path}: most recent commit not yet tested")
            return True
    else:
        logger.debug(f"Need to test {test_file_path}: most recent commit not yet tested (ENOENT)")
        return True

# search all files in a directory to see if a particular commit is present
def commit_is_present(repo, dirpath, target_commit):
    logger = logging.getLogger(__file__)

    if os.path.isdir(dirpath):
        commit = None
        for f in os.listdir(dirpath):
            fcommit = get_last_commit(repo, os.path.join(dirpath,f))
            if fcommit == target_commit:
                return True
        return False

def is_test_needed(repo, test_file, output_directory):
    logger = logging.getLogger(__file__)
    (test_commit,timestamp)   = get_last_commit(repo, test_file)
    testing_needed = commit_is_newer(repo, output_directory, test_file, timestamp)
    if testing_needed: 
        logger.info(f"Latest version of {test_file} ({test_commit[-5:]}) has not yet been tested")
        return (True,test_commit)
        # Run the test script
        #os.system(f"./scripts/setup_lustre_cluster.py {test_file}")
        #print(f"Test run for {test_file}")

        # Commit the output file
        #repo.git.add(output_file)
        #commit_message = f"Update output for {test_file}"
        #repo.git.commit('-m', commit_message)
        #print(f"Committed changes for {output_file}")
    else:
        logger.debug(f"No need to run test for {test_file}")
        return (False,None)

def run_command(command):
    logger = logging.getLogger(__file__)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()
    if stdout:
        logger.info(stdout.strip())
    if stderr:
        logger.error(stderr.strip())
    return process.returncode

def monitor_tests(repo,incoming_output_dir):
    logger = logging.getLogger(__file__)
    logger.debug(f"Working with repo {repo.working_tree_dir}")
    test_dir = os.path.join(repo.working_tree_dir, 'scripts/ansible')
    
    # Scan for test files
    logger.debug(f"Searching for new test files in {test_dir}")
    test_files = [f for f in os.listdir(test_dir) if f.startswith('autotest')]
    for test_file in test_files: 
        test_file_path   = os.path.join(test_dir, test_file)
        output_dir       = os.path.join(repo.working_tree_dir, incoming_output_dir, test_file)
        (needed,commit) = is_test_needed(repo, test_file_path, output_dir)
        if needed:
            os.makedirs(output_dir, exist_ok=True)
            ret = []
            mylog = f"{output_dir}/{__file__.split('/')[-1]}.log"
            logger.info(f"Logging into {mylog}")
            with open(mylog, 'w') as file:
                command = ["sudo", "./setup_lustre_cluster.py", test_file_path]
                command += ['--output_dir', '/'.join(output_dir.split('/')[0:-1])]
                command += ['--rebuild', 'vms', '--rebuild', 'network']
                #command += ['--skip', 'config', '--skip', 'test']
                #command += ['--rebuild', 'all']
                file.write(f'Autorunning {test_file} with commit {commit}.\n')
                file.write(f'COMMAND = {" ".join(command)}\n')
                logger.info(f'COMMAND = {" ".join(command)}\n')
                ret.append(run_command(command))
                file.write(f'Autoran {test_file} with commit {commit}: {ret[-1]}.\n')
            ret.append(repo.git.add(output_dir))
            ret.append(repo.git.commit('-m', f"automated run of {test_file}: {ret}"))
            ret.append(repo.git.push())
            logger.info(f"Ran {test_file} into {output_dir}: {ret}")

def print_uncommitted_files(repo):
    logger = logging.getLogger(__file__)
    try:
        changed_files = [item.a_path for item in repo.index.diff(None)]
        if changed_files:
            logger.debug("WARNING: Uncommitted files:")
            for file in changed_files:
                logger.debug(f"\t{file}")
    except git.exc.InvalidGitRepositoryError:
        logger.error("Error initializing git repository.")

def get_repo(path='.'):
    logger = logging.getLogger(__file__)
    def find_repo_root(path='.'):
        try:
            # Initialize a repo at the given path and climb to the root
            repo = git.Repo(path, search_parent_directories=True)
            # Return the git repo's working directory
            return repo.working_tree_dir
        except git.exc.InvalidGitRepositoryError:
            return None

    repo_root = find_repo_root(path)
    if repo_root is None:
        logger.error("No git repository found at specified path.")
        return

    logger.debug(f"Git Repository Root: {repo_root}")  # Diagnostic output

    try:
        repo = git.Repo(repo_root)
        return repo
    except git.exc.InvalidGitRepositoryError:
        logger.error("Error initializing git repository.")
        sys.exit(0)

def Fatal(msg):
    logger = logging.getLogger(__file__)
    logger.error(f"FATAL ERROR: {msg}")
    sys.exit(-1)

def die_if_root():
    # Check if script is run as root
    if os.geteuid() == 0:
        Fatal("Must be run as regular user")

def main():
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose logging")
    parser.add_argument('-l', '--log', type=str, help="Log file to write logging output to")
    args = parser.parse_args()

    die_if_root()

    # Setup logger based on arguments
    logger = setup_logger(args.verbose, args.log)
    # Example log messages
    #logger.debug("This is a debug message")
    #logger.info("This is an informational message")
    #logger.warning("This is a warning")
    #logger.error("This is an error message")
    #logger.critical("This is a critical message")

    repo = get_repo()
    print_uncommitted_files(repo)
    monitor_tests(repo,'scripts/output')

if __name__ == "__main__":
    main()



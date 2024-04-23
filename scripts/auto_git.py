#! /usr/bin/env python3.8

import argparse
import git
import logging
import os

def setup_logger(verbose, logfile):
    # Create a logger
    logger = logging.getLogger(__name__)
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

def get_last_commit(repo, path):
    logger = logging.getLogger(__name__)
    def actual_last_commit(repo, file_path):
        commits = list(repo.iter_commits(paths=file_path, max_count=1))
        if commits:
            last = commits[0].hexsha
        else:
            last = None
        logger.debug(f"Last commit for {file_path}: {last}")
        return last

    if os.path.isdir(path):
        commit = None
        for f in os.listdir(path):
            commit = actual_last_commit(repo, os.path.join(path,f))
            if commit:
                return commit
        return None
    else:
        return actual_last_commit(repo, path)

def is_test_needed(repo, test_file, output_directory):
    logger = logging.getLogger(__name__)
    test_commit   = get_last_commit(repo, test_file)
    output_commit = get_last_commit(repo, output_directory)
    if test_commit != output_commit:
        logger.debug(f"Test commit for {test_file}:{test_commit[-5:]} != Output commit for {output_directory}:{output_commit}")
        return True
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
        return False

def monitor_tests(repo):
    logger = logging.getLogger(__name__)
    logger.debug(f"Working with repo {repo.working_tree_dir}")
    test_dir = os.path.join(repo.working_tree_dir, 'scripts/ansible')
    output_dir = os.path.join(repo.working_tree_dir, 'scripts/output')
    
    # Scan for test files
    logger.debug(f"Searching for new test files in {test_dir}")
    test_files = [f for f in os.listdir(test_dir) if f.startswith('hosts')]
    for test_file in test_files: 
        test_file_path   = os.path.join(test_dir, test_file)
        output_dir       = os.path.join(repo.working_tree_dir, 'scripts/output', test_file)
        is_test_needed(repo, test_file_path, output_dir)

def print_uncommitted_files(repo):
    logger = logging.getLogger(__name__)
    try:
        changed_files = [item.a_path for item in repo.index.diff(None)]
        if changed_files:
            logger.debug("WARNING: Uncommitted files:")
            for file in changed_files:
                logger.debug(f"\t{file}")
    except git.exc.InvalidGitRepositoryError:
        logger.error("Error initializing git repository.")

def get_repo(path='.'):
    logger = logging.getLogger(__name__)
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

def main():
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose logging")
    parser.add_argument('-l', '--log', type=str, help="Log file to write logging output to")
    args = parser.parse_args()

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
    monitor_tests(repo)

if __name__ == "__main__":
    main()



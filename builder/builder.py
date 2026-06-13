import argparse
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import os

import arrow
from python_on_whales import docker, DockerException
import yaml

class Builder:
    def __init__(self, repository="ghcr.io/dekeyrej", tag="dev", build="None"):
        self.tags = ["dev", "test", "prod"]
        self.repository = repository
        self.tag = tag
        self.build = build
        with open("dependencies.yaml", "r") as f:  # load reverse-dependencies from dependencies.yaml (we want to know which microservices depend on which files, not the other way around)
            self.dependencies = yaml.safe_load(f)

        with open("microservices.yaml", "r") as f: # load microservice:application mapping from microservices.yaml
            self.microservices = yaml.safe_load(f)

        with open("last_build.yaml", "r") as f:    # read last build date/time from last_build.yaml
            self.last_build = arrow.get(yaml.safe_load(f)["last_build"])

    def find_modified_files(self):
        # Loop through parent directory and its subdirectories only (not sub-subdirectories), 
        # looking for *.py, *.toml, and Dockerfile files and check if they have been modified since the last build
        ignores = ["builder", "yaml", "helm", "tests", ".git", "instructions"]
        modified_files = []
        for root, dirs, files in os.walk(".."):
            if any(ignore in root for ignore in ignores):
                continue
            if root.count(os.sep) > 1:
                continue
            for file in files:
                logging.debug(f"{root}, {dirs}, {files}")
                if file.endswith(".py") or file.endswith(".toml") or file == "Dockerfile":
                    file_path = os.path.join(root, file)
                    if arrow.get(os.path.getmtime(file_path)) > self.last_build:
                        modified_files.append(file_path[3:])  # Remove the "./" from the beginning of the path
        return modified_files
    
    def determine_builds(self, modified_files):
        builds = set()
        for file in modified_files:
            for deps, microservice in self.dependencies.items():
                if file in deps:
                    if microservice == "all":
                        logging.debug(f"{file} is used by all microservices")
                        builds = set(self.microservices.keys())
                        break
                    logging.debug(f"{file} is used by {microservice}")
                    builds.add(microservice)
        return builds
    
    def build_microservices(self, builds, repository, tag, all_tags=False):
        successes = 0
        failures = []
        
        context = ".."
        dockerfile = "../Dockerfile"
        platforms = ["linux/amd64"]

        for build in builds:
            build_args = {"APPLICATION": self.microservices[build], "MICROSERVICE": build}
            tags = [f"{repository}/{build}:{t}" for t in self.tags] if all_tags else [f"{repository}/{build}:{tag}"]
            try:
                docker.build(context_path=context, file=dockerfile, build_args=build_args, 
                             platforms=platforms, tags=tags, push=True)
            
                logging.info(f"Built and pushed {repository}/{build}:{tag}")
                successes += 1
            except DockerException as e:
                logging.error(f"Failed to build {repository}/{build}:{tag}")
                logging.error(f"Error details: {e}")
                failures.append(build)

        buildcount = len(builds)
        if buildcount > 0 and successes == buildcount:
            logging.info("All builds succeeded")
            with open("last_build.yaml", "w") as f:
                yaml.safe_dump({"last_build": arrow.now().format()}, f)
        elif buildcount > 0:
            logging.info(f"{successes}/{buildcount} builds succeeded")
            if failures:
                logging.info("Failed builds:")
                for failure in failures:
                    logging.info(failure)

    def run(self, all_tags=False, build_all=False):
        if build_all:
            logging.info("Building all microservices due to --build-all flag")
            builds = set(self.microservices.keys())
        elif self.build != "None":
            logging.info(f"Building specified microservice: {self.build}")
            builds = {self.build}
        else:
            modified_files = self.find_modified_files()
            if not modified_files:
                logging.info("No modified files since last build")
                return
            else:
                logging.info("Modified files since last build:")
                for file in modified_files:
                    logging.info(file)
            builds = self.determine_builds(modified_files)
            
        if builds:
            logging.info("Microservices to build:")
            for build in builds:
                logging.info(build)
            self.build_microservices(builds, self.repository, tag, all_tags=all_tags)
        else:
            logging.info("No microservices need to be built")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build and push Docker images for modified microservices")
    ap.add_argument("--repository", type=str, default="ghcr.io/dekeyrej", help="Docker repository to push images to (default: ghcr.io/dekeyrej)")
    ap.add_argument("--tag", type=str, default="dev", help="Tag to use for the built images (default: dev)")
    ap.add_argument("--build", type=str, default="None", help="Build execute (default: None)")
    ap.add_argument("--all-tags", action="store_true", help="Build and push images for all tags (overrides --tag)")
    ap.add_argument("--all-builds", action="store_true", help="Build and push images for all microservices, regardless of modified files")
    args = ap.parse_args()
    
    repository = args.repository
    tag = args.tag
    build = args.build
    all_tags = args.all_tags
    all_builds = args.all_builds
    
    builder = Builder(repository, tag, build).run(all_tags=all_tags, build_all=all_builds)

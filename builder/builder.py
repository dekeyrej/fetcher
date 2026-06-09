import argparse
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import os

import arrow
from python_on_whales import docker, DockerException
import yaml

class Builder:
    def __init__(self, repository="ghcr.io/dekeyrej", tag="dev"):
        self.tags = ["dev", "test", "prod"]
        self.repository = repository
        self.tag = tag
        with open("dependencies.yaml", "r") as f:
            self.dependencies = yaml.safe_load(f)

        with open("microservices.yaml", "r") as f:
            self.microservices = yaml.safe_load(f)

        with open("last_build.yaml", "r") as f:
            self.last_build = arrow.get(yaml.safe_load(f)["last_build"])

    def find_modified_files(self):
        # Loop through subdirectories only (not current directory, not sub-subdirectories), 
        # looking for .py files and check if they have been modified since the last build
        modified_files = []
        for root, dirs, files in os.walk(".."):
            if root == "./builder":
                continue
            if root.count(os.sep) > 1:
                continue
            for file in files:
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
        buildcount = 0
        failures = []
        for build in builds:
            buildcount += 1
            app = self.microservices[build]
            if all_tags:
                tags = [f"{repository}/{build}:{t}" for t in self.tags]
            else:
                tags = f"{repository}/{build}:{tag}"
            try:
                docker.build(context_path="..", file="../Dockerfile", build_args={"APPLICATION": app, "MICROSERVICE": build}, 
                             platforms=["linux/amd64"], tags=tags, push=True)
            
                logging.info(f"Built and pushed {repository}/{build}:{tag}")
                successes += 1
            except DockerException as e:
                logging.error(f"Failed to build {repository}/{build}:{tag}")
                logging.error(f"Error details: {e}")
                failures.append(build)
                
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
    ap.add_argument("--all-tags", action="store_true", help="Build and push images for all tags (overrides --tag)")
    ap.add_argument("--build-all", action="store_true", help="Build and push images for all microservices, regardless of modified files")
    args = ap.parse_args()
    
    repository = args.repository
    tag = args.tag
    all_tags = args.all_tags
    build_all = args.build_all
    
    builder = Builder(repository, tag).run(all_tags=all_tags, build_all=build_all)

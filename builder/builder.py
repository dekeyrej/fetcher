# ToDo:
# - add argparse for tag, all-tags, build-all, repository
# - expand changed file selection to include .toml, and top-level Dockerfile


import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import os

import arrow
from python_on_whales import docker, DockerException
import yaml

class Builder:
    def __init__(self, repository="ghcr.io/dekeyrej", tag="dev"):
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
            if root == "." or root == "./builder":
                continue
            if root.count(os.sep) > 1:
                continue
            for file in files:
                if file.endswith(".py"):
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
    
    def build_microservices(self, builds, repository, tag):
        successes = 0
        buildcount = 0
        failures = []
        for build in builds:
            buildcount += 1
            app = self.microservices[build]
            try:
                docker.build(context_path="..", file="../Dockerfile", build_args={"APPLICATION": app, "MICROSERVICE": build}, 
                             platforms=["linux/amd64"], tags=f"{repository}/{build}:{tag}", push=True)
            
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

    def run(self):
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
            logging.debug("Microservices to build:")
            for build in builds:
                logging.debug(build)
            self.build_microservices(builds, self.repository, self.tag)
        else:
            logging.info("No microservices need to be built")

if __name__ == "__main__":
    repository="ghcr.io/dekeyrej"
    tag="prod"
    builder = Builder(repository, tag).run()

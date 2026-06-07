# Smart image builder
- Gathers list of files modified since `last_built` date.
- Using `reverse dependencies` determines which microservices need to be rebuilt.
- Executes `docker buildx build ...` via `python_on_whales` package using a common Dockerfile
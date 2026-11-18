# Skopeo Image Pusher

Use GitHub Actions + Skopeo to mirror public Docker Hub, GHCR, Quay, and Kubernetes container images to Aliyun ACR, without a local Docker daemon or `docker pull`.

Inspired by [tech-shrimp/docker_image_pusher](https://github.com/tech-shrimp/docker_image_pusher). This is an independently implemented minimal version, using an explicit source-to-destination mapping and `skopeo copy --all`.

## 1. Create an Aliyun ACR namespace and repository

Open https://cr.console.aliyun.com/ and create an ACR instance/namespace. **Before mirroring, create a destination repository** for each target name in `images.txt` (e.g. `alpine`). ACR may not permit the first push to create a repository automatically.

Copy the registry **hostname** (without `https://` or a namespace) from your ACR console. ACR endpoints vary by account/instance.

## 2. Set repository secrets

GitHub repository -> Settings -> Secrets and variables -> Actions -> New repository secret:

| Secret | Example |
|---|---|
| `ALIYUN_REGISTRY` | `registry.cn-hangzhou.aliyuncs.com` or your `crpi-...` hostname |
| `ALIYUN_NAME_SPACE` | `my-images` |
| `ALIYUN_REGISTRY_USER` | your ACR username |
| `ALIYUN_REGISTRY_PASSWORD` | your ACR registry login password |
| `DOCKERHUB_USER` | optional, for Docker Hub authenticated pulls |
| `DOCKERHUB_TOKEN` | optional, Docker Hub access token |

Never commit passwords or tokens to files.

## 3. Add images

Edit `images.txt`: **each active line contains exactly two whitespace-delimited fields**:

```text
docker.io/library/alpine:3.20 alpine:3.20
docker.io/library/redis:7.4 redis:7.4
ghcr.io/owner/project:v1.0 owner-project:v1.0
```

The second field is **repository:tag**, not a full registry address. Targets are constructed as `${ALIYUN_REGISTRY}/${ALIYUN_NAME_SPACE}/${TARGET}`.

Source must be a fully qualified image reference with its tag or digest. For Docker Hub official images, use `docker.io/library/...`. Comments start with `#`. Images with the same basename can map to different target names.

Commit to the `main` branch to trigger synchronization. The action also runs when the workflow or sync script changes.

## 4. Manual sync (one image)

Actions -> `Mirror container images to Aliyun ACR` -> Run workflow:

- `source_image`: `docker.io/library/redis:7.4`
- `target_image`: `redis:7.4`

Both fields must be supplied together. Leave both blank to mirror the entire manifest.

## 5. Verify

Check Actions job logs and the job summary. The resulting image can be pulled with:

```bash
podman login <ACR_HOSTNAME>
podman pull <ACR_HOSTNAME>/<NAMESPACE>/redis:7.4
```

## Notes / limitations

- Skopeo transfers image data through the **GitHub-hosted runner**, not directly between registries. It doesn't store a full local Docker image, but uses runner network, memory, and potentially temporary disk space.
- `--all` attempts to preserve a multi-architecture manifest list/index. Some ACR editions or upstream formats may reject it; errors are reported, not silently changed to a single architecture.
- Destination repository creation is not automated. Registry service quotas/permissions and Docker Hub rate limits still apply.
- Public source images work without source credentials; private upstream registries require additional auth logic.
- This workflow is **not** an ACR pull-through cache, image signing pipeline, or recursive tag synchronizer. Only listed tags are copied.
- The `push` trigger is for branch `main`. Change it if your default branch differs.
- GitHub-hosted runners have resource/time limits. Very large images may exceed them.

# Optional CXAS UNet weights (offline / faster first start)

On first run, **cxas-api** downloads `UNet_ResNet50_default.pth` (~841 MB) into the
`cxas_cache` Docker volume.

To skip the download, place the file here:

```text
cxas/weights/UNet_ResNet50_default.pth
```

Then restart: `docker compose up -d --force-recreate cxas-api`

The compose file mounts this directory read-only at `/data/local_weights` inside the container.

# ClearVoice PYMSS Stage adapter

Native source: FC-TTD/ClearerVoice-Studio main 6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61. Existing upstream algorithms and precision retained. New isolated provider, not an edit to the original clearervoice deployment. Stage h-7eeb8d0d97f78e3f uses image sha256:bfd1b25c21f10468f149ec1e736376e060c54bd86a15db1f21049886784e0fa3; docs added after that source snapshot, runtime source unchanged.

## Runtime and contract

`deploy.py` snapshots native py/config + this folder, verifies native bytes against commit, builds cached official-runtime overlay on ttd-edge, composes only owned clearvoice-audio-preview. Network10.41/24; GPU0 UUID5dda4827-a51a-2d06-53e3-1171bb3c8a60; private100.15:17902. Existing services/GPU allocations untouched. Stage web proxies /api/speech; no formal/public/Hub route. Model cache /mnt/TTD-Data/clearvoice-audio-preview read-only, own result root /mnt/TTD/04_应用/clearvoice-audio-preview; existing PYMSS jobs mounted /studio-inputs read-only. Family route edge via100.1 unchanged.

`models-lock.json` pins author revisions/SHA/size. `prepare.py` on edge only downloads/reuses exact pinned artifacts into its own NAS cache. `smoke.py` validates all5 native CUDA outputs and strict tensor matching; availability depends on worker/native/model-lock verification key. CPU-only `test_state.py` tests protocol independently, never substitutes for inference.

Compatible JSON API: GET models/jobs/batches, POST batches(model/stems/purpose), reuse(asset_id), start, exports(tracks); FileResponse result/WAV/ZIP +900 stream peaks + Range. IDs prefixed cv-, model IDs cv:. Never accepts arbitrary server paths. Input assets originate from PYMSS pool, first upload once there, pool batch never started. CV consumes only canonical asset via source metadata and shared NAS. No copies; cleanup must account for cross-provider references. Source pool may remain preparing; this is intentional, not active inference.

Serial GPU child process per job, resource preflight/wait10min, input/results retained, success skipped on retry; fail on missing tensor/shape. Maintenance blocks starts and deployment checks no worker/smoke active. Restart recovery marks incomplete work interrupted while preserving success. Exports bounded20inputs/2GiB and400selectedtracks,64KiB request, unique temp and atomic writes; browser save not guaranteed by ZIP generation.

## Inference details and limits

MOSS SS16k: native full pass bounded8s /6s hop, overlap correlation selects permutation/polarity, linear OLA. A/B is not verified stable speaker identity through long silences. SS12sec fixture first overlap6s SI-SDR10.314dB, full3.098, mixture0.140 (+2.958). MOSS SR48k: pad native input context/hop, trim actual model output to exact duration, never zero-pad output; min source16k, supplement estimated details not original restoration. Tested2.3976875sec115089frames. SE48k/FRCRN16k/GAN16k strict native outputs pass. Export48kPCM24 doesn't turn16k native content into true48k. Each child exits to release VRAM.

Tests: /data/smoke-report.json, /data/objective-smoke.json, /data/verified-models.json. PYMSS browser integration evidence ../pymss-ui-evidence/clearvoice-20261026 (workspace-relative). Real SS/SR/SE and CV→Instvox source reuse completed; zero new uploads; waveform/Range206/2track ZIP CRC+exactWAV hashes passed. Quality listening, long speaker identity, actual homeMac/mobile, browser save, host restart/rollback NOT_RUN.

## Deployment and rollback

Run python3 deploy/audio-preview/deploy.py from canonical checkout, never legacy dirtyJuly worktree. Verify nfs, no network overlap, owned container/image, idle provider; deploy script maintenance guard. Labels record content release; actual SHA must be captured. No broad prune or other service stop. Baseline cached image pinned ff9a24184aa1; no dependency upgrades.

Rollback UI separately to previous static image while preserving10.35 and shared PYMSS runtime. Provider can remain to preserve results; if rolling its own app use previous managed snapshot/Compose only when idle, preserve all NAS data, model cache, immutable source references and10.41. No rollback rehearsal or host restart claimed. Formal promotion pending user Stage listening confirmation and existing source commit/publication rules; no push authorization.

# ClearVoice audio adapter workspace

Read ../../work/PROJECT_STATE.md and TTD:/00_项目/共享测试部署标准.md, plus deploy/audio-preview/README.md. Isolated canonical checkout6b3774; do not modify legacy dirty ClearerVoice-Studio at workspace root or native algorithm source. New changes live in deploy/audio-preview only. No commits/push/formal promotion on this 2026-10-26 candidate. Stage previews only. Preserve GPU UUID/precision, native strict weight matching, model-lock pinned hashes and availability proof keys; worker/native/model artifact changes require new real5-model verification. Never delete or copy PYMSS immutable inputs; cross-provider references need lifecycle checks. Keep existing services and formal msst untouched. See UI work/pymss-webui AGENTS for customer category and Chinese>=12px rules.

## 2026-10-27 consumer entry publication

User separately authorized local commits for this adapter and the PYMSS/YingMusic consumers, then publication at http://msst/ui/ for LAN quality testing. This supersedes the earlier no-commit/candidate-only wording for source preparation. No push is authorized. Keep the existing managed edge provider running; record its exact image/source/Compose as a shared dependency. This entry promotion does not adopt the provider into Hub, change native inference, restart original ClearVoice or migrate NAS data.

## Hub受管接入（2026-10-27）
# clearvoice-hub Hub adapter

Canonical FC-TTD/ClearerVoice-Studio hub branch. User authorized this adoption, source push, model credentials, and controlled replacement after native acceptance/drain. Keep original model/weight verification, native queue and precision; no CPU/offload or model code edits. Only the per-job GPU worker goes through SDK; accepted background work and queue protection span its actual completion. Unknown execution keeps inputs/results/lease and cannot replay. Never commit media, weights, credentials or server state.

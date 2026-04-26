ACT_PLATFORM_UBUNTU_24_04 := catthehacker/ubuntu:act-latest
ACT_DEPLOY_FLAGS := -P ubuntu-24.04=$(ACT_PLATFORM_UBUNTU_24_04)

.PHONY: act-test-publish act-test-sync-wiki

act-test-publish:
	act push -W .github/workflows/deploy-pages.yml -j build -n $(ACT_DEPLOY_FLAGS) --var GCP_WORKLOAD_IDENTITY_PROVIDER=dummy --var GCP_SERVICE_ACCOUNT=dummy@example.iam.gserviceaccount.com --var GOOGLE_DRIVE_ROOT_FOLDER_ID=dummy --var GOOGLE_DRIVE_SHARED_DRIVE_ID=dummy --var GOOGLE_WORKSPACE_USER=dummy@example.com --var GOOGLE_DRIVE_PATH=dummy

act-test-sync-wiki:
	act push -W .github/workflows/sync-wiki.yml -j publish-wiki -n

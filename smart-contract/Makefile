.PHONY: all install build test clean deploy-sepolia deploy-mainnet test-network

DEPLOY_SCRIPT := scripts/Deploy.s.sol:DeployScript

all: build

install:
	curl -L https://foundry.paradigm.xyz | bash
	foundryup
	forge install foundry-rs/forge-std

build:
	forge build

test:
	forge test -vvv

clean:
	forge clean

deploy-sepolia:
	@set -a && . ./.dev.env && set +a && \
	forge script $(DEPLOY_SCRIPT) \
		--rpc-url $$SEPOLIA_RPC_URL \
		--private-key $$PRIVATE_KEY \
		--broadcast \
		--verify \
		--etherscan-api-key $$ETHERSCAN_API_KEY \
		-vvvv && \
	ADDR=$$(python3 -c "import json; d=json.load(open('broadcast/Deploy.s.sol/11155111/run-latest.json')); print(d['transactions'][0]['contractAddress'])") && \
	if grep -q "^CONTRACT_ADDRESS=" .dev.env; then \
		sed -i '' "s|^CONTRACT_ADDRESS=.*|CONTRACT_ADDRESS=$$ADDR|" .dev.env; \
	else \
		printf "\nCONTRACT_ADDRESS=$$ADDR" >> .dev.env; \
	fi && \
	echo "Saved CONTRACT_ADDRESS=$$ADDR to .dev.env"

deploy-mainnet:
	@set -a && . ./.prod.env && set +a && \
	forge script $(DEPLOY_SCRIPT) \
		--rpc-url $$MAINNET_RPC_URL \
		--private-key $$PRIVATE_KEY \
		--broadcast \
		--verify \
		--etherscan-api-key $$ETHERSCAN_API_KEY \
		-vvvv && \
	ADDR=$$(python3 -c "import json; d=json.load(open('broadcast/Deploy.s.sol/1/run-latest.json')); print(d['transactions'][0]['contractAddress'])") && \
	if grep -q "^CONTRACT_ADDRESS=" .prod.env; then \
		sed -i '' "s|^CONTRACT_ADDRESS=.*|CONTRACT_ADDRESS=$$ADDR|" .prod.env; \
	else \
		printf "\nCONTRACT_ADDRESS=$$ADDR" >> .prod.env; \
	fi && \
	echo "Saved CONTRACT_ADDRESS=$$ADDR to .prod.env"

test-network:
	@cd ts-test && \
	[ -d node_modules ] || npm install --silent && \
	set -a && . ../.dev.env && set +a && \
	npm test

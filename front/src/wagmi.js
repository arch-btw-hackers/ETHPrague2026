import '@rainbow-me/rainbowkit/styles.css';
import { getDefaultConfig } from '@rainbow-me/rainbowkit';
import { mainnet, base, polygon, optimism, arbitrum } from 'wagmi/chains';
import {
    injectedWallet,
    rainbowWallet,
    walletConnectWallet,
    coinbaseWallet,
    trustWallet,
    ledgerWallet
} from '@rainbow-me/rainbowkit/wallets';

export const config = getDefaultConfig({
    appName: 'wallet-connect',
    projectId: 'e21c759ddabfdee2fce1c526b96833cd',
    chains: [mainnet, base, polygon, optimism, arbitrum],
    ssr: false,
    wallets: [
        {
            groupName: 'Popular',
            wallets: [
                injectedWallet,
                rainbowWallet,
                coinbaseWallet,
                walletConnectWallet,
                trustWallet,
                ledgerWallet,
            ],
        },
    ],
});
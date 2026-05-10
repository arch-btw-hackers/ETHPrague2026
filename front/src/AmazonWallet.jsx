import React, { useState } from 'react';
import { ConnectButton } from '@rainbow-me/rainbowkit';
import { useAccount, useWriteContract, useWaitForTransactionReceipt } from 'wagmi';
import { CONTRACT_ADDRESS, CONTRACT_ABI, STATIC_RECEIVER, TRACKER_SERVICE_WALLET, API_BASE } from './constants';
import './AmazonWallet.css';

const AmazonWallet = () => {
    const { address, isConnected } = useAccount();

    const [temp, setTemp] = useState('23');
    const [overload, setOverload] = useState('5');
    const [status, setStatus] = useState('');

    const { data: hash, writeContractAsync, isPending } = useWriteContract();
    const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

    const handleAuthAndSend = async () => {
        if (!isConnected) {
            alert("Please connect your wallet first!");
            return;
        }

        try {
            setStatus('Initializing package...');

            const res = await fetch(`${API_BASE}/packages/initialize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    temp_c: parseFloat(temp),
                    acceleration: parseFloat(overload),
                }),
            });

            if (!res.ok) {
                const errBody = await res.text();
                throw new Error(`API error ${res.status}: ${errBody}`);
            }

            const data = await res.json();

            setStatus('Confirm in wallet...');

            const txHash = await writeContractAsync({
                address: CONTRACT_ADDRESS,
                abi: CONTRACT_ABI,
                functionName: 'createShipment',
                args: [
                    STATIC_RECEIVER,
                    TRACKER_SERVICE_WALLET,
                    data.package_ref,
                ],
            });
        } catch (error) {
            setStatus(`Error: ${error.shortMessage || error.message || 'Transaction failed'}`);
        }
    };

    return (
        <div className="a-page">
            <header className="checkout-header">
                <div><a href="/" className="nav-logo-link"></a></div>
                <h1 className="secure-checkout-title">Secure checkout</h1>
                <div><div className="nav-cart-icon"></div></div>
            </header>

            <main className="checkout-container">
                <div className="checkout-left-col">
                    <div className="checkout-card">
                        <h2>1. Select a delivery address</h2>
                        <div className="empty-state-text">Default address: Nashville 37217</div>
                        <div className="address-actions" style={{ marginTop: '10px' }}>
                            <button className="btn-add-address">Add a new delivery address</button>
                        </div>
                    </div>

                    <div className="checkout-card">
                        <h2>2. Transport Conditions</h2>
                        <div className="conditions-container">
                            <div className="condition-item">
                                <label>Temperature (°C)</label>
                                <input
                                    type="number"
                                    className="amazon-number-input"
                                    value={temp}
                                    onChange={(e) => setTemp(e.target.value)}
                                    step="0.1"
                                />
                            </div>
                            <div className="condition-item">
                                <label>Acceleration Overload</label>
                                <input
                                    type="number"
                                    className="amazon-number-input"
                                    value={overload}
                                    onChange={(e) => setOverload(e.target.value)}
                                    step="0.001"
                                />
                            </div>
                        </div>
                    </div>

                    <div className="checkout-card">
                        <h2>3. Payment method</h2>
                        <div style={{ marginTop: '15px' }}>
                            <ConnectButton showBalance={false} accountStatus="address" />
                        </div>
                    </div>

                    <div className="checkout-card">
                        <h2>4. Review items and shipping</h2>
                        <div className="empty-state-text">Review your order details before confirming.</div>
                    </div>
                </div>

                <aside className="checkout-right-col">
                    <div className="summary-card">
                        <button
                            className="btn-primary-action"
                            onClick={handleAuthAndSend}
                            disabled={!isConnected || isPending || isConfirming || isSuccess}
                            style={{ opacity: (!isConnected || isPending || isConfirming) ? 0.6 : 1 }}
                        >
                            {!isConnected ? "Connect Wallet"
                                : isPending ? "Confirm in Wallet..."
                                : isConfirming ? "Processing..."
                                : isSuccess ? "Payment Confirmed ✓"
                                : "Sign and Buy"}
                        </button>

                        {(status || isSuccess) && (
                            <div style={{
                                textAlign: 'center',
                                fontSize: isSuccess ? '14px' : '11px',
                                marginTop: '10px',
                                color: isSuccess ? 'green' : status.includes('Error') ? 'red' : '#c45500',
                                wordBreak: 'break-word'
                            }}>
                                {isSuccess ? (
                                    <div style={{ textAlign: 'center' }}>
                                        <strong style={{ display: 'block', marginBottom: '8px', fontSize: '14px', color: 'green' }}>Shipment created on-chain!</strong>
                                        <div style={{ display: 'inline-block', color: '#0f1111', fontSize: '13px', lineHeight: '1.5' }}>
                                            You can view status of your package
                                            <button 
                                                onClick={() => window.open('https://protozoan-mankind-rogue.ngrok-free.dev/', '_blank')}
                                                style={{
                                                    display: 'block',
                                                    margin: '15px auto',
                                                    padding: '4px 12px',
                                                    backgroundColor: '#ffd814',
                                                    color: '#0f1111',
                                                    border: '1px solid #fcd200',
                                                    borderRadius: '8px',
                                                    cursor: 'pointer',
                                                    fontWeight: 'bold',
                                                    boxShadow: '0 2px 5px 0 rgba(213,217,217,.5)',
                                                    whiteSpace: 'nowrap'
                                                }}
                                            >
                                                here
                                            </button>
                                        </div>
                                    </div>
                                ) : (
                                    <span style={{ fontWeight: 'bold' }}>{status}</span>
                                )}
                            </div>
                        )}

                        <hr className="summary-divider" />
                        <h3 style={{ fontSize: '16px', margin: '0 0 15px 0' }}>Order Summary</h3>
                        <div className="summary-row"><span>Items:</span><span>--</span></div>
                        <div className="summary-row"><span>Shipping:</span><span>--</span></div>
                        <hr className="summary-divider" />
                        <div className="summary-row total"><span>Order total:</span><span>$0.00</span></div>
                    </div>
                </aside>
            </main>

            <footer className="checkout-footer">
                <p>

                    <a href="/cart">Back to cart</a>
                </p>
            </footer>
        </div>
    );
};

export default AmazonWallet;
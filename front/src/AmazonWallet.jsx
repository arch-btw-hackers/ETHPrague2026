import React, { useState } from 'react';
import { ConnectButton } from '@rainbow-me/rainbowkit';
import { useAccount, useSignMessage } from 'wagmi';
import './AmazonWallet.css';

const AmazonWallet = () => {
    const { address, isConnected } = useAccount();
    const { signMessageAsync } = useSignMessage();

    const [temp, setTemp] = useState('23');
    const [overload, setOverload] = useState('5');
    const [status, setStatus] = useState('');

    const handleAuthAndSend = async () => {
        if (!isConnected) {
            alert("Please connect your wallet first!");
            return;
        }

        try {
            setStatus('Getting nonce...');
            const nonceRes = await fetch(`http://80.211.207.162:8000/api/v1/auth/nonce?wallet_address=${address}`);
            const nonceData = await nonceRes.json();
            const serverNonce = nonceData.nonce;

            const domain = window.location.host;
            const origin = window.location.origin;
            const issuedAt = new Date().toISOString();

            const siweMessage = `${domain} wants you to sign in with your Ethereum account:
${address}

I accept the Amazon Terms of Service.

URI: ${origin}
Version: 1
Chain ID: 1
Nonce: ${serverNonce}
Issued At: ${issuedAt}`;

            setStatus('Please sign the SIWE message...');
            const signature = await signMessageAsync({ message: siweMessage });

            setStatus('Verifying...');
            const finalPayload = {
                message: siweMessage,
                signature: signature,
                wallet_address: address,
                payload: {
                    device_id: "cargo_tracker_9000",
                    nonce: serverNonce,
                    readings: {
                        temp_c: parseFloat(temp),
                        acceleration_overload: parseFloat(overload)
                    }
                }
            };

            const response = await fetch('http://80.211.207.162:8000/api/v1/auth/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(finalPayload),
            });

            const resultData = await response.json();

            if (response.ok) {
                setStatus('Success!');
                alert("Order processed and signed successfully!");
            } else {
                const errorMsg = typeof resultData.detail === 'object'
                    ? JSON.stringify(resultData.detail)
                    : resultData.detail;
                setStatus(`Error: ${errorMsg || 'Verification failed'}`);
            }
        } catch (error) {
            setStatus(`Error: ${error.message || 'Server unavailable'}`);
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
                            disabled={!isConnected}
                            style={{ opacity: isConnected ? 1 : 0.6 }}
                        >
                            {isConnected ? "Sign and Buy" : "Connect Wallet"}
                        </button>

                        {status && (
                            <div style={{
                                textAlign: 'center',
                                fontSize: '11px',
                                marginTop: '10px',
                                color: status.includes('Error') ? 'red' : '#c45500',
                                fontWeight: 'bold',
                                wordBreak: 'break-word'
                            }}>
                                {status}
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
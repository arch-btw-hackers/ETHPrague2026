import React from 'react';
import './AmazonWallet.css';

const AmazonWallet = () => {
    return (
        <div>
            <header className="checkout-header">
                <div>
                    <a href="/" className="nav-logo-link"></a>
                </div>
                <h1 className="secure-checkout-title">Secure checkout</h1>
                <div>
                    <div className="nav-cart-icon"></div>
                </div>
            </header>

            <main className="checkout-container">
                <div className="checkout-left-col">
                    <div className="checkout-card">
                        <h2>Select a delivery address</h2>
                    </div>

                    <div className="checkout-card">
                        <h2>Add delivery or pickup address</h2>
                        <div className="empty-state-text">
                            Enter your address to see delivery options
                        </div>
                        <div className="address-actions">
                            <button className="btn-add-address">Add a new delivery address</button>
                            <button className="btn-add-address">Find a pickup location nearby</button>
                        </div>
                    </div>

                    <div className="checkout-card">
                        <h2>Conditions</h2>
                        <div className="conditions-container">
                            <div className="condition-item">
                                <label>Temperature (°C)</label>
                                <input
                                    type="number"
                                    className="amazon-number-input"
                                    placeholder="22.5"
                                    step="0.1"
                                />
                            </div>
                            <div className="condition-item">
                                <label>Acceleration Overload</label>
                                <input
                                    type="number"
                                    className="amazon-number-input"
                                    placeholder="3.067"
                                    step="0.001"
                                />
                            </div>
                        </div>
                    </div>

                    <div className="checkout-card">
                        <h2>Payment method</h2>
                    </div>

                    <div className="checkout-card">
                        <h2>Review items and shipping</h2>
                    </div>
                </div>

                <aside className="checkout-right-col">
                    <div className="summary-card">
                        <button className="btn-primary-action">Deliver to this address</button>
                        <hr className="summary-divider" />
                        <h3 style={{ fontSize: '16px', margin: '0 0 15px 0' }}>Order Summary</h3>
                        <div className="summary-row">
                            <span>Items:</span>
                            <span>--</span>
                        </div>
                        <div className="summary-row">
                            <span>Shipping & handling:</span>
                            <span>--</span>
                        </div>
                        <div className="summary-row">
                            <span>Estimated tax to be collected:</span>
                            <span>--</span>
                        </div>
                        <hr className="summary-divider" />
                        <div className="summary-row total">
                            <span>Order total:</span>
                            <span>$0.00</span>
                        </div>
                    </div>
                </aside>
            </main>

            <footer className="checkout-footer">
                <p>
                    Why has sales tax been applied? <a href="#">See tax and seller information.</a>
                </p>
                <p>
                    Do you need help? Explore our <a href="#">Help pages</a> or <a href="#">contact us</a>
                </p>
                <p>
                    For an item sold by Amazon.com: When you click the "Place your order" button, we'll send you an email message acknowledging receipt of your order. Your contract to purchase an item will not be complete until we send you an email notifying you that the item has been shipped.
                </p>
                <p>
                    Colorado Purchasers: <a href="#">Important information regarding sales tax you may owe in your State</a>
                </p>
                <p>
                    Within 30 days of delivery, you may return new, unopened merchandise in its original condition. Exceptions and restrictions apply. See Amazon.com's <a href="#">Returns Policy</a>
                </p>
                <p>
                    <a href="#">Back to cart</a>
                </p>
            </footer>
        </div>
    );
};

export default AmazonWallet;
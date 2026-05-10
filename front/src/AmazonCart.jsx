import React from 'react';
import { useNavigate } from 'react-router-dom';
import './AmazonCart.css';

const AmazonCart = () => {
    const navigate = useNavigate();

    return (
        <div className="a-page">
            <header>
                <div className="nav-belt">
                    <div className="nav-left">
                        <a href="/" className="nav-logo-link"></a>
                    </div>
                    <div className="nav-location">
                        Delivering to Nashville 37217<br />
                        <b>Update location</b>
                    </div>
                    <div className="nav-fill-search">
                        <div className="nav-search-bar">
                            <select className="nav-search-dropdown">
                                <option>All</option>
                            </select>
                            <input type="text" className="nav-input" placeholder="Search Amazon" />
                            <button className="nav-search-submit">🔍</button>
                        </div>
                    </div>
                    <div className="nav-right-tools">
                        <div className="nav-tool-item">
                            <span className="line-2">🇺🇸 EN ▾</span>
                        </div>
                        <div className="nav-tool-item">
                            <span className="line-1">Hello, Customer</span>
                            <span className="line-2">Account & Lists ▾</span>
                        </div>
                        <div className="nav-tool-item">
                            <span className="line-1">Returns</span>
                            <span className="line-2">& Orders</span>
                        </div>
                        <div className="nav-tool-item nav-cart">
                            <span className="nav-cart-count">0</span>
                            <div className="nav-cart-icon"></div>
                            <span className="line-2" style={{ marginTop: '12px' }}>Cart</span>
                        </div>
                    </div>
                </div>
                <div className="nav-main">
                    <div style={{ fontWeight: 'bold' }}>☰ All</div>
                    <div style={{ background: 'white', color: 'black', borderRadius: '20px', padding: '4px 12px', fontSize: '12px', fontWeight: 'bold' }}>Rufus</div>
                    <div style={{ fontWeight: 'bold', marginLeft: '5px' }}>Join Prime</div>
                    <div>Health AI</div>
                    <div>1 Hour Delivery</div>
                    <div>Amazon Haul</div>
                    <div>Medical Care ▾</div>
                    <div>Prime Video</div>
                    <div>Today's Deals</div>
                </div>
            </header>
            <main className="sc-page-content">
                <div style={{ flex: 1 }}>
                    <div className="sc-card visa-banner">
                        <img src="https://m.media-amazon.com/images/G/01/credit/CBCC/acq-marketing/maple/Q123-1103_US_CBCC_ACQ_Maple_Thumbnail_126x80._CB613265021_.png" alt="Visa" />
                        <div className="text">
                            You can <b>get $50 off instantly</b> upon approval for <b>Amazon Visa.</b>
                        </div>
                        <button>Learn more</button>
                    </div>
                    <div className="sc-card">
                        <h1 style={{ fontSize: '28px', fontWeight: '500', marginBottom: '15px' }}>Your Amazon Cart is empty</h1>
                        <p style={{ fontSize: '14px', lineHeight: '20px' }}>
                            Your Shopping Cart lives to serve. Give it purpose — fill it with groceries, clothing, household supplies, electronics, and more.
                            Continue shopping on the <a href="#" style={{ color: '#007185', textDecoration: 'none' }}>Amazon.com homepage</a>, learn about <a href="#" style={{ color: '#007185', textDecoration: 'none' }}>today's deals</a>, or visit your <a href="#" style={{ color: '#007185', textDecoration: 'none' }}>Wish List</a>.
                        </p>
                    </div>
                    <div className="sc-card">
                        <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '15px' }}>Your Items</h2>
                        <div className="tabs-container">
                            <div className="tab active">No items saved for later</div>
                            <div className="tab">Buy it again</div>
                        </div>
                        <div style={{ padding: '30px', textAlign: 'center', border: '1px solid #ddd', borderRadius: '4px' }}>
                            No items
                        </div>
                    </div>
                </div>
                <aside className="sc-right-col">
                    <div className="sc-subtotal-box">
                        <div className="sc-subtotal-text">
                            Subtotal (0 items): <b>$0.00</b>
                        </div>
                        <button className="btn-proceed" onClick={() => navigate('/checkout')}>
                            Proceed to checkout
                        </button>
                    </div>
                </aside>
            </main>
            <footer>
                <div className="footer-top">Back to top</div>
                <div className="footer-main">
                    <div className="footer-grid">
                        <div className="footer-col">
                            <h3>Get to Know Us</h3>
                            <ul><li>Careers</li><li>Blog</li><li>About Amazon</li></ul>
                        </div>
                        <div className="footer-col">
                            <h3>Make Money with Us</h3>
                            <ul><li>Sell on Amazon</li><li>Become an Affiliate</li></ul>
                        </div>
                        <div className="footer-col">
                            <h3>Amazon Payment</h3>
                            <ul><li>Amazon Visa</li><li>Shop with Points</li></ul>
                        </div>
                        <div className="footer-col">
                            <h3>Let Us Help You</h3>
                            <ul><li>Your Account</li><li>Your Orders</li><li>Help</li></ul>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    );
};

export default AmazonCart;

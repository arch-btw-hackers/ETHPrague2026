import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import AmazonCart from './AmazonCart';
import AmazonWallet from './AmazonWallet';
import AlzaCart from './AlzaCart';
import AlzaPayment from './AlzaPayment';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<AmazonCart />} />
        <Route path="/cart" element={<AmazonCart />} />
        <Route path="/checkout" element={<AmazonWallet />} />
        <Route path="/alza" element={<AlzaCart />} />
        <Route path="/alza-payment" element={<AlzaPayment />} />
      </Routes>
    </Router>
  );
}

export default App;
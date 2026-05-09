import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import AmazonCart from './AmazonCart';
import AmazonWallet from './AmazonWallet';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<AmazonCart />} />
        <Route path="/checkout" element={<AmazonWallet />} />
      </Routes>
    </Router>
  );
}

export default App;
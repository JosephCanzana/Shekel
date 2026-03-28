-- ============================================================
-- DATABASE SCHEMA
-- ============================================================

-- App_Settings
CREATE TABLE IF NOT EXISTS App_Settings (
    id               INT          NOT NULL DEFAULT 1,
    user_counter     INT          NOT NULL DEFAULT 1000,
    counter_year     INT          NOT NULL,
    default_password VARCHAR(255) NOT NULL DEFAULT 'shekel123',
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT single_row CHECK (id = 1)
);

INSERT IGNORE INTO App_Settings (id, user_counter, counter_year, default_password)
VALUES (1, 1004, 2026, 'dudaY_2026');

-- ============================================================

-- Users
CREATE TABLE IF NOT EXISTS Users (
    user_id     INT          NOT NULL,
    first_name  VARCHAR(50)  NOT NULL,
    last_name   VARCHAR(50)  NOT NULL,
    role        ENUM('superadmin', 'cashier', 'stocking', 'admin') NOT NULL,
    password    VARCHAR(255) NOT NULL,
    status      ENUM('activated', 'not_activated', 'suspended', 'archived') NOT NULL,
    PRIMARY KEY (user_id)
);

INSERT IGNORE INTO Users (user_id, first_name, last_name, role, password, status)
VALUES (10002026, 'superadmin', 'account', 'superadmin',
        'pbkdf2:sha256:1000000$LBLb2g8SjudjJfx5$ec9566c749e82ab5b9c5d9eef49948ff1727bb0f3ff823dc9eeda986b8f445cf',
        'activated');

INSERT IGNORE INTO Users (user_id, first_name, last_name, role, password, status)
VALUES
    (10012026, 'coadmin',  'test', 'admin',
     'pbkdf2:sha256:1000000$LBLb2g8SjudjJfx5$ec9566c749e82ab5b9c5d9eef49948ff1727bb0f3ff823dc9eeda986b8f445cf',
     'activated'),
    (10022026, 'cashier',  'test', 'cashier',
     'pbkdf2:sha256:1000000$LBLb2g8SjudjJfx5$ec9566c749e82ab5b9c5d9eef49948ff1727bb0f3ff823dc9eeda986b8f445cf',
     'activated'),
    (10032026, 'stocking', 'test', 'stocking',
     'pbkdf2:sha256:1000000$LBLb2g8SjudjJfx5$ec9566c749e82ab5b9c5d9eef49948ff1727bb0f3ff823dc9eeda986b8f445cf',
     'activated');

-- ============================================================

-- Recovery_Details
CREATE TABLE IF NOT EXISTS Recovery_Details (
    user_id      INT          NOT NULL,
    email        VARCHAR(100) NOT NULL,
    phone_number VARCHAR(20)  NULL,
    reset_token  VARCHAR(255) NULL,
    token_expiry DATETIME     NULL,
    PRIMARY KEY (user_id),
    CONSTRAINT fk_recovery_user
        FOREIGN KEY (user_id) REFERENCES Users (user_id)
        ON UPDATE CASCADE ON DELETE CASCADE
);

-- ============================================================

-- Categories
CREATE TABLE IF NOT EXISTS Categories (
    category_id   INT          NOT NULL AUTO_INCREMENT,
    category_name VARCHAR(100) NOT NULL,
    description   TEXT         NULL,
    status        ENUM('active', 'inactive') NOT NULL DEFAULT 'active',
    PRIMARY KEY (category_id),
    CONSTRAINT uq_category_name UNIQUE (category_name)
);

-- ============================================================

-- Products
-- product_id is a user-entered barcode / SKU (e.g. "8851234567890", "COKE-SOLO")
CREATE TABLE IF NOT EXISTS Products (
    product_id            VARCHAR(100)   NOT NULL,
    product_name          VARCHAR(150)   NOT NULL,
    category_id           INT            NULL,
    unit_price            DECIMAL(10,2)  NOT NULL,
    revenue_price         DECIMAL(10,2)  NOT NULL,
    product_price         DECIMAL(10,2)  NOT NULL,    -- unit_price + revenue_price
    low_reorder_threshold INT            NOT NULL,
    status                ENUM('active', 'archived') NOT NULL,
    created_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id),
    CONSTRAINT fk_product_category
        FOREIGN KEY (category_id) REFERENCES Categories (category_id)
        ON UPDATE CASCADE ON DELETE SET NULL
);

-- ============================================================

-- ProductBundles
-- One optional bundle per product (e.g. Coke 12-pack barcode maps to Coke solo x24)
-- Scanning the bundle barcode during stock-in/sale multiplies by bundle_count
CREATE TABLE IF NOT EXISTS ProductBundles (
    bundle_id    VARCHAR(100) NOT NULL,               -- bundle barcode / SKU
    product_id   VARCHAR(100) NOT NULL,               -- FK -> Products (UNIQUE: one bundle per product)
    bundle_name  VARCHAR(100) NOT NULL,               -- e.g. "12-pack"
    bundle_count INT          NOT NULL,               -- units per bundle e.g. 24
    PRIMARY KEY (bundle_id),
    CONSTRAINT uq_bundle_product UNIQUE (product_id),
    CONSTRAINT fk_bundle_product
        FOREIGN KEY (product_id) REFERENCES Products (product_id)
        ON UPDATE CASCADE ON DELETE CASCADE
);

-- ============================================================

-- Inventory
CREATE TABLE IF NOT EXISTS Inventory (
    inventory_id       INT          NOT NULL AUTO_INCREMENT,
    product_id         VARCHAR(100) NOT NULL,
    quantity_available INT          NOT NULL DEFAULT 0,
    quantity_defective INT          NOT NULL DEFAULT 0,
    last_updated       DATETIME     NOT NULL,
    PRIMARY KEY (inventory_id),
    CONSTRAINT uq_inventory_product UNIQUE (product_id),
    CONSTRAINT fk_inventory_product
        FOREIGN KEY (product_id) REFERENCES Products (product_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================

-- Stock_In
CREATE TABLE IF NOT EXISTS Stock_In (
    stockin_id        INT          NOT NULL AUTO_INCREMENT,
    product_id        VARCHAR(100) NOT NULL,
    user_id           INT          NOT NULL,
    quantity_received INT          NOT NULL,
    stockin_datetime  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes             TEXT         NULL,
    PRIMARY KEY (stockin_id),
    CONSTRAINT fk_stockin_product
        FOREIGN KEY (product_id) REFERENCES Products (product_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_stockin_user
        FOREIGN KEY (user_id) REFERENCES Users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================

-- Sales
CREATE TABLE IF NOT EXISTS Sales (
    transaction_id      INT           NOT NULL AUTO_INCREMENT,
    sale_datetime       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id             INT           NOT NULL,
    total_unit_price    DECIMAL(10,2) NOT NULL,
    total_revenue_price DECIMAL(10,2) NOT NULL,
    total_amount        DECIMAL(10,2) NOT NULL,
    payment_method      VARCHAR(50)   NULL,
    PRIMARY KEY (transaction_id),
    CONSTRAINT fk_sales_user
        FOREIGN KEY (user_id) REFERENCES Users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================

-- Sales_Details
CREATE TABLE IF NOT EXISTS Sales_Details (
    sale_detail_id        INT           NOT NULL AUTO_INCREMENT,
    transaction_id        INT           NOT NULL,
    product_id            VARCHAR(100)  NOT NULL,
    quantity              INT           NOT NULL,
    unit_price_at_sale    DECIMAL(10,2) NOT NULL,
    revenue_price_at_sale DECIMAL(10,2) NOT NULL,
    price_at_sale         DECIMAL(10,2) NOT NULL,
    subtotal_unit         DECIMAL(10,2) NOT NULL,
    subtotal_revenue      DECIMAL(10,2) NOT NULL,
    subtotal_amount       DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (sale_detail_id),
    CONSTRAINT fk_saledetail_transaction
        FOREIGN KEY (transaction_id) REFERENCES Sales (transaction_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_saledetail_product
        FOREIGN KEY (product_id) REFERENCES Products (product_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================

-- Defects
CREATE TABLE IF NOT EXISTS Defects (
    defect_id           INT           NOT NULL AUTO_INCREMENT,
    defect_datetime     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id             INT           NOT NULL,
    total_unit_price    DECIMAL(10,2) NOT NULL,
    total_revenue_price DECIMAL(10,2) NOT NULL,
    total_amount        DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (defect_id),
    CONSTRAINT fk_defect_user
        FOREIGN KEY (user_id) REFERENCES Users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================

-- Defect_Details
CREATE TABLE IF NOT EXISTS Defect_Details (
    defect_detail_id        INT           NOT NULL AUTO_INCREMENT,
    defect_id               INT           NOT NULL,
    product_id              VARCHAR(100)  NOT NULL,
    quantity                INT           NOT NULL,
    reason                  ENUM('defect', 'damage', 'expired', 'change_of_mind') NOT NULL,
    compensation            ENUM('pending', 'loss', 'returned', 'replacement')    NOT NULL,
    unit_price_at_defect    DECIMAL(10,2) NOT NULL,
    revenue_price_at_defect DECIMAL(10,2) NOT NULL,
    price_at_defect         DECIMAL(10,2) NOT NULL,
    subtotal_unit           DECIMAL(10,2) NOT NULL,
    subtotal_revenue        DECIMAL(10,2) NOT NULL,
    subtotal_amount         DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (defect_detail_id),
    CONSTRAINT fk_defectdetail_defect
        FOREIGN KEY (defect_id) REFERENCES Defects (defect_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_defectdetail_product
        FOREIGN KEY (product_id) REFERENCES Products (product_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================

-- Audit_Log
CREATE TABLE IF NOT EXISTS Audit_Log (
    log_id          INT          NOT NULL AUTO_INCREMENT,
    user_id         INT          NOT NULL,
    action_type     ENUM('INSERT', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT') NOT NULL,
    module          ENUM('Products', 'Inventory', 'Sales', 'Defects', 'Users', 'Stock_In') NOT NULL,
    reference_id    VARCHAR(100) NULL,                -- VARCHAR to support both INT and String IDs
    reference_table VARCHAR(50)  NULL,
    description     TEXT         NOT NULL,
    action_datetime DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (log_id),
    CONSTRAINT fk_auditlog_user
        FOREIGN KEY (user_id) REFERENCES Users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);
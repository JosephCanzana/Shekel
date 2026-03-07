-- ============================================================
-- DATABASE SCHEMA
-- ============================================================

--  Users
CREATE TABLE IF NOT EXISTS Users (
    user_id     INT          NOT NULL AUTO_INCREMENT,
    first_name  VARCHAR(50)  NOT NULL, 
    last_name   VARCHAR(50)  NOT NULL, 
    role        ENUM('admin', 'cashier', 'stocking', 'co-admin') NOT NULL,
    password    VARCHAR(255) NOT NULL,         
    status      ENUM('activated', 'not_activated', 'suspended', 'archived') NOT NULL,
    PRIMARY KEY (user_id)
);

-- ============================================================

--  Recovery_Details
CREATE TABLE IF NOT EXISTS Recovery_Details (
    user_id        INT          NOT NULL,             -- PK + FK -> Users (Admin access only)
    email          VARCHAR(100) NOT NULL,             -- Recovery email address
    phone_number   VARCHAR(20)  NULL,                 -- Optional recovery phone
    reset_token    VARCHAR(255) NULL,                 -- Token for password reset
    token_expiry   DATETIME     NULL,                 -- Expiry for reset token
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
    PRIMARY KEY (category_id),
    CONSTRAINT uq_category_name UNIQUE (category_name)
);

-- ============================================================

--  Products
CREATE TABLE IF NOT EXISTS Products (
    product_id            INT            NOT NULL AUTO_INCREMENT,
    product_name          VARCHAR(150)   NOT NULL,
    category_id           INT            NULL,        -- FK -> Categories
    unit_price            DECIMAL(10,2)  NOT NULL,    -- Cost / purchase price
    revenue_price         DECIMAL(10,2)  NOT NULL,    -- Target revenue price
    product_price         DECIMAL(10,2)  NOT NULL,    -- Selling price to customer
    low_reorder_threshold INT            NOT NULL,    -- Alert trigger quantity
    status                ENUM('active', 'archived') NOT NULL,
    created_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id),
    CONSTRAINT fk_product_category
        FOREIGN KEY (category_id) REFERENCES Categories (category_id)
        ON UPDATE CASCADE ON DELETE SET NULL
);

-- ============================================================

--  Inventory
CREATE TABLE IF NOT EXISTS Inventory (
    inventory_id        INT      NOT NULL AUTO_INCREMENT,
    product_id          INT      NOT NULL,            -- FK -> Products (UNIQUE: one record per product)
    quantity_available  INT      NOT NULL DEFAULT 0,  -- Current sellable stock
    quantity_defective  INT      NOT NULL DEFAULT 0,  -- Damaged / expired stock
    last_updated        DATETIME NOT NULL,            -- Auto-updated on change
    PRIMARY KEY (inventory_id),
    CONSTRAINT uq_inventory_product UNIQUE (product_id),
    CONSTRAINT fk_inventory_product
        FOREIGN KEY (product_id) REFERENCES Products (product_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================

--  Stock_In
CREATE TABLE IF NOT EXISTS Stock_In (
    stockin_id        INT      NOT NULL AUTO_INCREMENT,
    product_id        INT      NOT NULL,              -- FK -> Products
    user_id           INT      NOT NULL,              -- FK -> Users (Stocking account who logged it)
    quantity_received INT      NOT NULL,
    stockin_datetime  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes             TEXT     NULL,                  -- Optional remarks (e.g. batch info)
    PRIMARY KEY (stockin_id),
    CONSTRAINT fk_stockin_product
        FOREIGN KEY (product_id) REFERENCES Products (product_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_stockin_user
        FOREIGN KEY (user_id) REFERENCES Users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================

--  Sales
CREATE TABLE IF NOT EXISTS Sales (
    transaction_id        INT           NOT NULL AUTO_INCREMENT,
    sale_datetime         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id               INT           NOT NULL,     -- FK -> Users (Cashier who processed the sale)
    total_unit_price      DECIMAL(10,2) NOT NULL,     -- Sum of cost prices
    total_revenue_price   DECIMAL(10,2) NOT NULL,     -- Sum of revenue prices
    total_amount          DECIMAL(10,2) NOT NULL,     -- Total charged to customer
    payment_method        VARCHAR(50)   NULL,          -- cash, card, etc. (future use)
    PRIMARY KEY (transaction_id),
    CONSTRAINT fk_sales_user
        FOREIGN KEY (user_id) REFERENCES Users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================

-- Sales_Details
CREATE TABLE IF NOT EXISTS Sales_Details (
    sale_detail_id          INT           NOT NULL AUTO_INCREMENT,
    transaction_id          INT           NOT NULL,   -- FK -> Sales
    product_id              INT           NOT NULL,   -- FK -> Products
    quantity                INT           NOT NULL,
    unit_price_at_sale      DECIMAL(10,2) NOT NULL,   -- Snapshot at time of sale
    revenue_price_at_sale   DECIMAL(10,2) NOT NULL,   -- Snapshot at time of sale
    price_at_sale           DECIMAL(10,2) NOT NULL,   -- Snapshot at time of sale
    subtotal_unit           DECIMAL(10,2) NOT NULL,   -- unit_price x quantity
    subtotal_revenue        DECIMAL(10,2) NOT NULL,   -- revenue_price x quantity
    subtotal_amount         DECIMAL(10,2) NOT NULL,   -- price x quantity
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
    defect_id             INT           NOT NULL AUTO_INCREMENT,
    defect_datetime       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id               INT           NOT NULL,     -- FK -> Users (User who logged the defect)
    total_unit_price      DECIMAL(10,2) NOT NULL,
    total_revenue_price   DECIMAL(10,2) NOT NULL,
    total_amount          DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (defect_id),
    CONSTRAINT fk_defect_user
        FOREIGN KEY (user_id) REFERENCES Users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================

-- Defect_Details
CREATE TABLE IF NOT EXISTS Defect_Details (
    defect_detail_id         INT           NOT NULL AUTO_INCREMENT,
    defect_id                INT           NOT NULL,  -- FK -> Defects
    product_id               INT           NOT NULL,  -- FK -> Products
    quantity                 INT           NOT NULL,
    reason                   ENUM('defect', 'damage', 'expired', 'change_of_mind') NOT NULL,
    compensation             ENUM('pending', 'loss', 'returned', 'replacement')    NOT NULL,
    unit_price_at_defect     DECIMAL(10,2) NOT NULL,  -- Snapshot at time of logging
    revenue_price_at_defect  DECIMAL(10,2) NOT NULL,
    price_at_defect          DECIMAL(10,2) NOT NULL,
    subtotal_unit            DECIMAL(10,2) NOT NULL,
    subtotal_revenue         DECIMAL(10,2) NOT NULL,
    subtotal_amount          DECIMAL(10,2) NOT NULL,
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
    user_id         INT          NOT NULL,            -- FK -> Users
    action_type     ENUM('INSERT', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT') NOT NULL,
    module          ENUM('Products', 'Inventory', 'Sales', 'Defects', 'Users', 'Stock_In') NOT NULL,
    reference_id    INT          NULL,                -- ID of the affected record
    reference_table VARCHAR(50)  NULL,                -- Table name the reference_id belongs to
    description     TEXT         NOT NULL,            -- Human-readable summary of what happened
    action_datetime DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (log_id),
    CONSTRAINT fk_auditlog_user
        FOREIGN KEY (user_id) REFERENCES Users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

INSERT INTO Users (first_name, last_name, role, password, status)
VALUES ('admin', 'account', 'admin', 'pbkdf2:sha256:1000000$LBLb2g8SjudjJfx5$ec9566c749e82ab5b9c5d9eef49948ff1727bb0f3ff823dc9eeda986b8f445cf', 'not_activated');
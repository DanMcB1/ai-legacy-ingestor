      *****************************************************************
      * LAKESIDE AUTO GROUP (SAMPLE) -- LEGACY DMS DEAL EXTRACT
      * FIXED-LENGTH CUSTOMER / DEAL RECORD FROM THE MAINFRAME.
      * THIS FILE IS FICTIONAL DEMO DATA, NOT A REAL CUSTOMER FILE.
      *****************************************************************
       01  DEAL-RECORD.
           05  CUST-ID          PIC 9(8).
           05  CUST-NAME        PIC X(30).
           05  CUST-STATUS      PIC X.
           05  CUST-TYPE        REDEFINES CUST-STATUS PIC X.
           05  STORE-ID         PIC X(4).
           05  VIN              PIC X(17).
           05  DEAL-DATE        PIC 9(8).
           05  GROSS-AMT        PIC S9(9)V99 COMP-3.
           05  NET-AMT          PIC S9(7)V99 COMP-3.
           05  VEHICLE-COUNT    PIC 9(2).
           05  VEHICLE-INFO     OCCURS 2 TIMES.
               10  VEH-YEAR     PIC 9(4).
               10  VEH-MAKE     PIC X(12).
           05  FILLER           PIC X(5).

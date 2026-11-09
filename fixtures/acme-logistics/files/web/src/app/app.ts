import { Component } from '@angular/core';
import { InvoicesPage } from './invoices/invoices';
import { ShipmentsPage } from './shipments/shipments';

@Component({
  selector: 'acme-root',
  standalone: true,
  imports: [ShipmentsPage, InvoicesPage],
  template: `
    <h1>Acme Logistics</h1>
    <acme-shipments />
    <acme-invoices />
  `,
})
export class App {}

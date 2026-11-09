import { Component, inject } from '@angular/core';
import { ApiClient, Invoice } from '../api/client';

@Component({
  selector: 'acme-invoices',
  standalone: true,
  template: `
    <h2>Invoices</h2>
    <input [value]="shipmentId" (change)="show($any($event.target).value)" />
    <ul>
      @for (invoice of invoices; track invoice.number) {
        <li>{{ invoice.number }}: {{ invoice.total }} RSD</li>
      }
    </ul>
  `,
})
export class InvoicesPage {
  private readonly api = inject(ApiClient);

  shipmentId = '';
  invoices: Invoice[] = [];

  show(shipmentId: string): void {
    this.shipmentId = shipmentId;
    this.api.invoices(shipmentId).subscribe((invoices) => (this.invoices = invoices));
  }
}

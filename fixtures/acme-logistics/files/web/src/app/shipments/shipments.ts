import { Component, OnInit, inject } from '@angular/core';
import { ApiClient, BookingRequest, Shipment } from '../api/client';
import { quote } from './pricing';

@Component({
  selector: 'acme-shipments',
  standalone: true,
  template: `
    <h2>Shipments</h2>
    <ul>
      @for (shipment of shipments; track shipment.id) {
        <li>{{ shipment.trackingNumber }}: {{ shipment.status }}</li>
      }
    </ul>
    <p>Estimated price: {{ estimate() }} RSD</p>
    <button (click)="book()">Book</button>
  `,
})
export class ShipmentsPage implements OnInit {
  private readonly api = inject(ApiClient);

  shipments: Shipment[] = [];
  form: BookingRequest = {
    sender: '',
    recipient: '',
    address: '',
    weightKg: 1,
    lengthCm: 20,
    widthCm: 15,
    heightCm: 10,
    express: false,
    remoteZone: false,
  };

  ngOnInit(): void {
    this.load();
  }

  estimate(): number {
    return quote(this.form);
  }

  book(): void {
    this.api.book(this.form).subscribe(() => this.load());
  }

  private load(): void {
    this.api.shipments(this.form.recipient).subscribe((shipments) => (this.shipments = shipments));
  }
}

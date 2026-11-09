import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export interface Shipment {
  id: string;
  trackingNumber: string;
  recipient: string;
  status: string;
  price: number;
}

export interface Invoice {
  number: string;
  shipmentId: string;
  total: number;
}

export interface BookingRequest {
  sender: string;
  recipient: string;
  address: string;
  weightKg: number;
  lengthCm: number;
  widthCm: number;
  heightCm: number;
  express: boolean;
  remoteZone: boolean;
}

@Injectable({ providedIn: 'root' })
export class ApiClient {
  private readonly http = inject(HttpClient);

  shipments(recipient: string): Observable<Shipment[]> {
    return this.http.get<Shipment[]>('/api/shipments', { params: { recipient } });
  }

  book(request: BookingRequest): Observable<Shipment> {
    return this.http.post<Shipment>('/api/shipments', request);
  }

  invoices(shipmentId: string): Observable<Invoice[]> {
    return this.http.get<Invoice[]>('/api/invoices', { params: { shipmentId } });
  }
}
